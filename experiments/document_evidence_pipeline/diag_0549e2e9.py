"""DIAGNOSIS ONLY — no production/staging code changed, no decoding params touched.

STEP 1-3: paper 0549e2e9 under legacy / content_aware@10 / content_aware@15.
STEP 4  : correlate @10 conformance vs selection composition across all 34 canonical
          papers; classify the 3 smaller regressions.
STEP 5  : medical ca@10 per-paper wall-clock vs conformance (parsed from cov_run.log).

Seeded path (temperature 0, seed 42).  Each 0549e2e9 request is PRIMED (matching the
real pipeline, which calls prime_ollama_cache) and issued twice to check byte-reproducibility.

  python -u experiments/document_evidence_pipeline/diag_0549e2e9.py
"""
from __future__ import annotations

import json
import re
import sys
import time
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import requests  # noqa: E402
from src.summarization import retrieval_aware as RA  # noqa: E402
from src.summarization import summarize as S  # noqa: E402
from src.evidence.anchors import find_anchors  # noqa: E402

CANON = HERE / "runs" / "prodab-20260902T004416Z" / "canonical"
COV = HERE / "runs" / "selection_policy"
OUTD = COV / "diag_0549e2e9"
OUTD.mkdir(parents=True, exist_ok=True)
TARGET = "0549e2e9e6bec759723fded85a49c2c076b6a978"
SMALL_REGR = ["a6ecdf69", "e6f1d66c", "ddb170b2"]
LLMCFG = {"base_url": "http://localhost:11434", "model": "qwen2.5:7b", "seed": 42}
OPTS = {"temperature": 0, "seed": 42, "top_p": 0.9, "top_k": 40, "repeat_penalty": 1.1}


def load_by_paper():
    ch = json.loads((CANON / "processed" / "chunks.json").read_text(encoding="utf-8"))
    by = {}
    for c in ch:
        by.setdefault(c["paper_id"], []).append(c)
    for p in by:
        by[p].sort(key=lambda c: c["chunk_index"])
    return by


def raw_call(system_prompt, user_content):
    nctx = S.estimate_num_ctx(user_content, system_prompt=system_prompt)
    r = requests.post("http://localhost:11434/api/chat", json={
        "model": "qwen2.5:7b",
        "messages": [{"role": "system", "content": system_prompt},
                     {"role": "user", "content": user_content}],
        "format": "json", "stream": False, "options": {**OPTS, "num_ctx": nctx},
    }, timeout=600).json()
    return {"content": r.get("message", {}).get("content", ""), "done_reason": r.get("done_reason"),
            "eval_count": r.get("eval_count"), "prompt_eval_count": r.get("prompt_eval_count"),
            "num_ctx": nctx}


def repetition_loop(text, minlen=40, mincount=5):
    n = len(text)
    for L in (60, 40):
        seen = Counter(text[i:i + L] for i in range(0, max(1, n - L), 5))
        for s, c in seen.most_common(3):
            if c > mincount and s.strip():
                return {"substr_len": L, "count": c, "sample": s[:60]}
    return None


def classify(resp):
    c = resp["content"]
    out = {"chars": len(c), "tokens_out": resp["eval_count"], "tokens_in": resp["prompt_eval_count"],
           "num_ctx": resp["num_ctx"], "done_reason": resp["done_reason"],
           "hit_limit": resp["done_reason"] == "length", "repetition_loop": repetition_loop(c)}
    try:
        parsed = json.loads(c)
        out["valid_json"] = True
        if isinstance(parsed, dict):
            keys = list(parsed.keys())
            schema = set(S._EXTRACTION_SCHEMA_KEYS)
            out["top_level_keys"] = keys
            out["nonconforming_keys"] = [k for k in keys if k not in schema and not str(k).startswith("_")]
            out["nested_string_fields"] = [k for k in S._STRING_EXTRACTION_FIELDS
                                           if isinstance(parsed.get(k), (dict, list))]
            out["schema_fields_present"] = [k for k in schema if parsed.get(k) not in (None, "", [], {})]
    except json.JSONDecodeError as e:
        out["valid_json"] = False
        out["parse_fail_offset"] = e.pos
        out["parse_fail_context"] = c[max(0, e.pos - 40):e.pos + 40]
        out["parse_fail_msg"] = str(e)
    if out["hit_limit"]:
        out["verdict"] = "TRUNCATION"
    elif out["repetition_loop"]:
        out["verdict"] = "REPETITION_LOOP"
    elif not out.get("valid_json"):
        out["verdict"] = "INVALID_JSON"
    elif out.get("nonconforming_keys") or out.get("nested_string_fields"):
        out["verdict"] = "VALID_BUT_WRONG_SHAPE"
    else:
        out["verdict"] = "OTHER (conforming)"
    return out


def composition(chunk_ids, by_id):
    rows = []
    for cid in chunk_ids:
        c = by_id.get(cid)
        if not c:
            continue
        rows.append({"chunk_id": cid, "section": c.get("section"), "block_type": c.get("block_type"),
                     "anchors": len(find_anchors(c["text"])), "chars": len(c["text"])})
    tbl = [r for r in rows if r["block_type"] == "table"]
    tot = max(sum(r["chars"] for r in rows), 1)
    return rows, {"n": len(rows), "total_chars": sum(r["chars"] for r in rows),
                  "table_share_count": round(len(tbl) / max(len(rows), 1), 3),
                  "table_share_chars": round(sum(r["chars"] for r in tbl) / tot, 3),
                  "total_anchors": sum(r["anchors"] for r in rows),
                  "distinct_sections": len({r["section"] for r in rows})}


def main():
    import chromadb
    from sentence_transformers import SentenceTransformer

    by_paper = load_by_paper()
    model = SentenceTransformer("BAAI/bge-m3", device="cuda")
    model.max_seq_length = 256
    gvecs = model.encode(RA._GENERIC_QUERIES, normalize_embeddings=True)
    col = chromadb.PersistentClient(path=str(CANON / "chroma_db")).get_collection("researchgpt_papers")

    def select(pid, mode, budget):
        pcs = by_paper[pid]
        if mode == "legacy":
            return RA._select_legacy(pcs, col, gvecs, pid, 2500)
        cfg = {**RA._SELECTION_DEFAULTS, "mode": "content_aware", "max_passages": budget}
        return RA._select_content_aware(pcs, col, model, pid, cfg, 2500)

    # ================= STEP 1 + 2 : 0549e2e9 raw + classify =================
    print("== STEP 1+2 : 0549e2e9 raw responses (primed, x2) ==")
    by_id_t = {c["chunk_id"]: c for c in by_paper[TARGET]}
    title = by_paper[TARGET][0]["title"]
    variants = {"legacy": select(TARGET, "legacy", None),
                "ca10": select(TARGET, "content_aware", 10),
                "ca15": select(TARGET, "content_aware", 15)}
    cls = {}
    for tag, (txt, tr) in variants.items():
        uc = f"Title: {title}\n\nText:\n{txt}"
        sysp = S.select_extraction_prompt(txt)[1]
        S.prime_ollama_cache(LLMCFG)
        r1 = raw_call(sysp, uc)
        S.prime_ollama_cache(LLMCFG)
        r2 = raw_call(sysp, uc)
        repro = r1["content"] == r2["content"]
        (OUTD / f"raw_{tag}.txt").write_text(r1["content"], encoding="utf-8")
        c1, c2 = classify(r1), classify(r2)
        cls[tag] = {**c1, "byte_reproducible_primed_2x": repro,
                    "verdict_stable_2x": c1["verdict"] == c2["verdict"],
                    "domain_variant": "cs_ml" if sysp == S.EXTRACTION_SYSTEM_PROMPT else "biomed"}
        print(f"\n[{tag}] byte_reproducible(primed x2)={repro}  verdict_stable_2x={c1['verdict']==c2['verdict']}")
        print(f"  chars={c1['chars']} tokens_out={c1['tokens_out']} tokens_in={c1['tokens_in']} "
              f"num_ctx={c1['num_ctx']} done_reason={c1['done_reason']}  VERDICT={c1['verdict']}")
        print(f"  valid_json={c1.get('valid_json')} nonconf_keys={c1.get('nonconforming_keys')} "
              f"nested={c1.get('nested_string_fields')} schema_fields_present={c1.get('schema_fields_present')}")
        if c1.get("parse_fail_context"):
            print(f"  parse fail @{c1['parse_fail_offset']}: {c1['parse_fail_context']!r}")
        if c1.get("repetition_loop"):
            print(f"  repetition: {c1['repetition_loop']}")
        print(f"  head: {r1['content'][:160]!r}")
        print(f"  tail: {r1['content'][-120:]!r}")

    # ================= STEP 3 : composition, @10 vs @15 =================
    print("\n== STEP 3 : 0549e2e9 selection composition ==")
    comp = {}
    for tag in ("legacy", "ca10", "ca15"):
        rows, agg = composition(variants[tag][1]["selected_chunk_ids"], by_id_t)
        comp[tag] = {"rows": rows, "agg": agg}
        print(f"[{tag}] {agg}")
    s10 = set(variants["ca10"][1]["selected_chunk_ids"])
    s15 = set(variants["ca15"][1]["selected_chunk_ids"])
    only15 = [c for c in variants["ca15"][1]["selected_chunk_ids"] if c not in s10]
    print(f"@15 is superset of @10: {s10 <= s15}")
    print(f"@15 adds (not in @10): " + ", ".join(
        f"{c[-8:]}(bt={by_id_t[c].get('block_type')},anc={len(find_anchors(by_id_t[c]['text']))},"
        f"ch={len(by_id_t[c]['text'])})" for c in only15))
    print(f"@10 adds (not in @15): {[c[-8:] for c in s10 - s15]}")

    # ================= STEP 4 : one paper or a class? =================
    print("\n== STEP 4 : @10 conformance vs selection composition (all 34 canonical) ==")
    ca10 = {r["paper_id"]: r for r in json.loads((COV / "cov_canon_ca10.json").read_text(encoding="utf-8"))}
    rows4 = []
    for pid in sorted(by_paper):
        if pid not in ca10:
            continue
        total_w = sum(len(c["text"].split()) for c in by_paper[pid])
        if total_w <= 2500:
            comp_agg = {"table_share_chars": None, "total_chars": None, "total_anchors": None, "distinct_sections": None}
            note = "passthrough(<=2500w)"
        else:
            _, comp_agg = composition(select(pid, "content_aware", 10)[1]["selected_chunk_ids"], {c["chunk_id"]: c for c in by_paper[pid]})
            note = ""
        rows4.append({"paper_id": pid, "conformance": ca10[pid]["conformance"], "n_fields": ca10[pid]["n"],
                      **comp_agg, "note": note})
    (OUTD / "step4_composition.json").write_text(json.dumps(rows4, indent=2), encoding="utf-8")

    def grp(pred):
        xs = [r for r in rows4 if pred(r) and r["table_share_chars"] is not None]
        if not xs:
            return "n=0"
        f = lambda k: sum(r[k] for r in xs) / len(xs)
        return (f"n={len(xs):2}  table_share_chars={f('table_share_chars'):.2f}  "
                f"total_chars={f('total_chars'):.0f}  total_anchors={f('total_anchors'):.0f}  "
                f"distinct_sections={f('distinct_sections'):.1f}")
    print(f"  conformant           : {grp(lambda r: r['conformance']=='conformant')}")
    print(f"  salvaged             : {grp(lambda r: r['conformance']=='salvaged')}")
    print(f"  nonconformant_unrep. : {grp(lambda r: r['conformance']=='nonconformant_unrepaired')}")
    print(f"  regressed (fields<legacy) papers get classified below")
    print("\n  per-paper (sorted by table_share_chars desc):")
    for r in sorted([r for r in rows4 if r["table_share_chars"] is not None],
                    key=lambda x: -x["table_share_chars"])[:12]:
        print(f"    {r['paper_id'][:12]} conf={r['conformance']:24} tbl_ch={r['table_share_chars']:.2f} "
              f"chars={r['total_chars']:>5} anchors={r['total_anchors']:>4} secs={r['distinct_sections']}")

    # 3 smaller regressions — capture raw @10, classify
    print("\n== STEP 4b : the 3 smaller canonical regressions, raw @10 ==")
    for pfx in SMALL_REGR:
        pid = next(p for p in by_paper if p.startswith(pfx))
        txt, tr = select(pid, "content_aware", 10)
        _, agg = composition(tr["selected_chunk_ids"], {c["chunk_id"]: c for c in by_paper[pid]})
        uc = f"Title: {by_paper[pid][0]['title']}\n\nText:\n{txt}"
        sysp = S.select_extraction_prompt(txt)[1]
        S.prime_ollama_cache(LLMCFG)
        cl = classify(raw_call(sysp, uc))
        print(f"  {pfx} conf(cov)={ca10[pid]['conformance']}/{ca10[pid]['n']}f  VERDICT={cl['verdict']}  "
              f"tokens_out={cl['tokens_out']} done={cl['done_reason']} nonconf={cl.get('nonconforming_keys')} "
              f"nested={cl.get('nested_string_fields')} tbl_ch={agg['table_share_chars']:.2f}")

    # ================= STEP 5 : medical timing =================
    print("\n== STEP 5 : medical ca@10 per-paper wall-clock vs conformance ==")
    log = (ROOT / ".." / "scratchpad").resolve()  # not used; parse the known log
    logtxt = Path("C:/Users/Praka/AppData/Local/Temp/claude/c--Users-Praka-Downloads-researchgpt-pipeline/"
                  "74c87135-1df4-47a4-9b82-725d040d87ec/scratchpad/cov_run.log").read_text(encoding="utf-8", errors="replace")
    seg = logtxt[logtxt.find("data_test regression"): logtxt.find("== medical_ca10")]
    med_ids = sorted({c["paper_id"] for c in json.loads((ROOT / "data/processed/chunks.json").read_text(encoding="utf-8")) if c.get("has_full_text")})
    medconf = {r["paper_id"]: r["conformance"] for r in json.loads((COV / "cov_medical_ca10.json").read_text(encoding="utf-8"))}
    bars = re.findall(r"(\d+)/19 \[(\d+:\d+:\d+|\d+:\d+)<[^,]+,\s*([\d.]+)s/it\]", seg)
    prev = 0.0
    print("  paper#  paper_id       elapsed_hms   step_s   conformance")
    for idx, hms, rate in bars:
        parts = [int(x) for x in hms.split(":")]
        secs = parts[0] * 3600 + parts[1] * 60 + parts[2] if len(parts) == 3 else parts[0] * 60 + parts[1]
        step = secs - prev
        prev = secs
        i = int(idx) - 1
        pid = med_ids[i] if i < len(med_ids) else "?"
        print(f"   {idx:>3}    {pid[:12]:12}  {hms:>11}   {step:>7.0f}   {medconf.get(pid, '?')}")

    (OUTD / "diag.json").write_text(json.dumps(
        {"step12": cls, "step3": comp, "step4": rows4}, indent=2, default=str), encoding="utf-8")
    print(f"\nwrote {OUTD}")


if __name__ == "__main__":
    main()
