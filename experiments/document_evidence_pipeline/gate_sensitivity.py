"""Mutation testing of the Stage-5 evidence gate — measures SENSITIVITY
(does it accept claims it should) alongside the by-construction specificity.

Ground truth is mechanical: the mutation class defines the expected verdict.
No human annotation. Does NOT tune thresholds.

Unit under test: src.evidence.gate._gate_value(field, value, chunks, surnames)
(the real production grounding + attribution + sanity + decide).

  python experiments/document_evidence_pipeline/gate_sensitivity.py --pass det   # deterministic classes
  python experiments/document_evidence_pipeline/gate_sensitivity.py --pass llm   # + LLM paraphrase
  python experiments/document_evidence_pipeline/gate_sensitivity.py --pass all
"""
from __future__ import annotations

import argparse
import json
import random
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import requests  # noqa: E402
from src.evidence.anchors import NUMERIC_ANCHOR_RE as _NUMVAL  # noqa: E402  (single source of truth)
from src.evidence.gate import _gate_value, _ground, _sig_tokens, _METRIC_TOKENS  # noqa: E402

OUT = HERE / "runs" / "gate_sensitivity"
LLM_SEED = 42
LLM_MODEL = "qwen2.5:7b"
LLM_URL = "http://localhost:11434/api/chat"

CORPORA = [
    ("canonical60",
     HERE / "runs/prodab-20260902T004416Z/canonical_paper_evidence.json",
     HERE / "runs/prodab-20260902T004416Z/canonical/processed/chunks.json",
     HERE / "runs/prodab-20260902T004416Z/canonical/raw_metadata/collected_papers.json"),
    ("data_test",
     HERE / "runs/staging-20260902T030714Z/paper_evidence.json",
     ROOT / "data_test/processed/chunks.json",
     ROOT / "data_test/raw_metadata/collected_papers.json"),
]

_MODEL_PREFIX = re.compile(
    r"(?:gpt|llama|qwen|mistral|mixtral|gemma|gemini|claude|bert|roberta|deberta|t5|"
    r"palm|phi|falcon|vicuna|command|search-r1|colnomic)[-\s]?$", re.I)


def _is_identifier_number(value: str, m: "re.Match[str]") -> bool:
    """True when this number is glued into a model / version token
    ('GPT-5.2', 'Llama-3', 'T3-59K', 'GPT-4.1-mini') rather than a free result number."""
    before = value[max(0, m.start() - 12):m.start()]
    after = value[m.end():m.end() + 2]
    if re.search(r"[A-Za-z]-$", before) or _MODEL_PREFIX.search(before):
        return True
    if after[:1].isalpha() or after[:1] in ("-",) and after[1:2].isdigit():
        return True
    return False


def load(corpus):
    name, ev, ch, meta = corpus
    E = json.loads(Path(ev).read_text(encoding="utf-8"))
    C = json.loads(Path(ch).read_text(encoding="utf-8"))
    M = json.loads(Path(meta).read_text(encoding="utf-8"))
    by_paper = defaultdict(list)
    for c in C:
        by_paper[c["paper_id"]].append(c)
    surn = {}
    for m in M:
        pid = m.get("paperId") or m.get("paper_id")
        surn[pid] = [a.get("name", "") for a in (m.get("authors") or []) if isinstance(a, dict)]
    items = []
    for rec in E:
        pid = rec["paper_id"]
        for field in ("metrics", "results"):
            for it in rec.get("evidence", {}).get(field, []):
                if it.get("final") == "RETURNED":
                    items.append({"corpus": name, "paper_id": pid, "field": field,
                                  "value": it["value"], "chunks": by_paper[pid],
                                  "surnames": surn.get(pid, [])})
    return items


def result_numbers(value: str) -> list[str]:
    """`_NUMVAL` numbers that are NOT part of a model/version identifier."""
    return [m.group(0) for m in _NUMVAL.finditer(value) if not _is_identifier_number(value, m)]


def not_in_any_chunk(num: str, chunks) -> bool:
    return not any(num in c.get("text", "") for c in chunks)


def perturb_number(num: str, chunks, rng: random.Random) -> str | None:
    """Return a different number string, guaranteed absent from every chunk."""
    for _ in range(40):
        if "." in num:
            whole, frac = num.split(".", 1)
            newfrac = str((int(frac) + rng.randint(11, 89)) % (10 ** len(frac))).zfill(len(frac))
            cand = f"{whole}.{newfrac}"
        else:
            cand = str(int(num) + rng.choice([7, 11, 13, 23, 31, -7, -13]))
            if int(cand) < 10:
                cand = str(int(num) + 40)
        if cand != num and not_in_any_chunk(cand, chunks):
            return cand
    return None


# ---------------------------------------------------------------------------
# rule-based paraphrase (fully deterministic)
# ---------------------------------------------------------------------------
_VERB_SYN = [
    (r"\bachieved\b", "attained"), (r"\bachieves\b", "attains"),
    (r"\breached\b", "hit"), (r"\bobtained\b", "recorded"),
    (r"\bshowed\b", "exhibited"), (r"\bshows\b", "exhibits"),
    (r"\bdemonstrated\b", "displayed"), (r"\bimproved\b", "boosted"),
    (r"\bincreased\b", "rose"), (r"\boutperformed\b", "surpassed"),
    (r"\boutperform\b", "surpass"), (r"\bfound\b", "observed"),
    (r"\breveals?\b", "indicates"), (r"\bpresents?\b", "reports"),
]
_NOUN_SYN = [
    (r"\bthe system\b", "the pipeline"), (r"\bthe approach\b", "the method"),
    (r"\bthe best configuration\b", "the top configuration"),
    (r"\bthe best-performing variant\b", "the strongest variant"),
    (r"\bthe evaluation\b", "the assessment"), (r"\bthe largest model\b", "the biggest model"),
    (r"\bbaseline\b", "reference model"),
]


def paraphrase_rule(value: str) -> list[str]:
    """Deterministic paraphrases of a RESULT SENTENCE that keep every number and
    every metric/dataset token. (Metric-name values are not sentences and are
    excluded upstream.)"""
    v = value.strip().rstrip(".")
    out = []
    # variant 1 — synonym substitution on non-anchor verbs/nouns
    s1 = v
    for pat, rep in _VERB_SYN + _NOUN_SYN:
        s1 = re.sub(pat, rep, s1, flags=re.I)
    if s1.lower() != v.lower():
        out.append(s1 + ".")
    # variant 2 — active -> passive for "SUBJ <verb> (an) REST [on/with TAIL]"
    m = re.match(r"^(.*?\b\w+) (attained|achieved|hit|recorded|reached|obtained|exhibited|"
                 r"displayed|showed|shows|demonstrated|reported|reports) (an? )?(.+?)"
                 r"(\s+(?:on|with|for|across) .+)?\.?$", v, re.I)
    if m:
        subj, _verb, _art, rest, tail = m.groups()
        out.append(f"{rest[0].upper()}{rest[1:]}{tail or ''} was recorded for {subj.strip().lower()}.")
    # variant 3 — clause reorder for a leading subordinate/comparative clause
    if ", " in v:
        head, _, rest = v.partition(", ")
        if len(rest) > 15 and not head.lower().startswith(("we ", "our ", "the ")):
            out.append(f"{rest[0].upper()}{rest[1:]} (here, {head.lower()}).")
    keep, src_nums = [], set(_NUMVAL.findall(value))
    src_metrics = _sig_tokens(value) & _METRIC_TOKENS
    for s in dict.fromkeys(out):
        if set(_NUMVAL.findall(s)) >= src_nums and (_sig_tokens(s) & _METRIC_TOKENS) >= src_metrics:
            keep.append(s)
    return keep


def paraphrase_llm(value: str, rng_seed: int = LLM_SEED) -> str | None:
    sys_p = ("Paraphrase the sentence. Keep EVERY number and EVERY metric or dataset name "
             "exactly as written. Return one sentence, nothing else.")
    payload = {"model": LLM_MODEL, "stream": False,
               "messages": [{"role": "system", "content": sys_p},
                            {"role": "user", "content": value}],
               "options": {"temperature": 0, "seed": rng_seed}}
    try:
        r = requests.post(LLM_URL, json=payload, timeout=120)
        r.raise_for_status()
        txt = r.json()["message"]["content"].strip().strip('"').split("\n")[0].strip()
        return txt or None
    except Exception as exc:  # noqa: BLE001
        return f"__LLM_ERROR__:{exc}"


# ---------------------------------------------------------------------------
def run_gate(field, value, chunks, surnames):
    it = _gate_value(field, value, chunks, surnames)
    return it["final"], it.get("abstain_reason") or it.get("attribution"), it


def supporting_chunk(field, value, chunks):
    g = _ground(value, chunks, field=field)
    return (g[0] if g else None)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pass", dest="phase", choices=["det", "llm", "all"], default="all")
    ap.add_argument("--no-range", action="store_true",
                    help="disable the metric-range-plausibility check (the pre-fix 'before' baseline)")
    args = ap.parse_args()
    if args.no_range:
        import src.evidence.gate as _G
        _G.metric_range_check = lambda v: None       # neutralise for the before/after comparison
        print("[--no-range] metric_range_check disabled for this run")
    OUT.mkdir(parents=True, exist_ok=True)
    rng = random.Random(20260902)

    base = []
    for cp in CORPORA:
        base += load(cp)
    print(f"base RETURNED quant items: {len(base)} "
          f"({sum(1 for b in base if b['field']=='metrics')} metrics / {sum(1 for b in base if b['field']=='results')} results)")

    mutants = []  # each: class, expected, corpus, paper_id, field, base_value, mutant_value, extra

    for b in base:
        f, v, ch, sn = b["field"], b["value"], b["chunks"], b["surnames"]
        base_final, base_reason, _ = run_gate(f, v, ch, sn)
        b["re_returns"] = (base_final == "RETURNED")
        rnums = result_numbers(v)

        # 1 NUMERIC PERTURBATION  (expected REJECT/ABSTAIN)
        for num in rnums:
            pert = perturb_number(num, ch, rng)
            if not pert:
                continue
            mv = v.replace(num, pert, 1)
            mutants.append({"cls": "numeric_perturbation", "expected": "ABSTAINED", **_slim(b),
                            "mutant_value": mv, "note": f"{num}->{pert}"})

        # 2a PARAPHRASE rule  (expected ACCEPT) — RESULT SENTENCES only
        if f == "results":
            for pv in paraphrase_rule(v):
                mutants.append({"cls": "paraphrase_rule", "expected": "RETURNED", **_slim(b),
                                "mutant_value": pv, "note": ""})

        # 3 FABRICATION  (expected REJECT)
        if f == "results":
            metric = next((t for t in _sig_tokens(v) & _METRIC_TOKENS), "score")
            fake = perturb_number(rnums[0] if rnums else "50", ch, rng) or "63.41"
            fv = f"Our method achieved a {metric} of {fake} on the held-out test set."
            if not_in_any_chunk(fake, ch):
                mutants.append({"cls": "fabrication", "expected": "ABSTAINED", **_slim(b),
                                "mutant_value": fv, "note": f"fake number {fake}"})

        # 4a SUPPORT DELETION — remove the single primary support chunk (corroboration probe)
        if b["re_returns"]:
            hit = supporting_chunk(f, v, ch)
            if hit is not None:
                mutants.append({"cls": "support_deletion_primary", "expected": "ABSTAINED", **_slim(b),
                                "mutant_value": v, "drop_chunk_ids": [hit.get("chunk_id")],
                                "note": "primary support chunk removed"})
        # 4b SUPPORT DELETION — remove EVERY chunk containing the value's numbers (true removal)
        if b["re_returns"] and rnums:
            drop = [c.get("chunk_id") for c in ch if any(n in c.get("text", "") for n in rnums)]
            if drop:
                mutants.append({"cls": "support_deletion_full", "expected": "ABSTAINED", **_slim(b),
                                "mutant_value": v, "drop_chunk_ids": drop,
                                "note": f"all {len(drop)} chunks with the number(s) removed"})

    # run deterministic mutants
    for m in mutants:
        ch = _chunks_for(base, m)
        if m["cls"].startswith("support_deletion"):
            drop = set(m.get("drop_chunk_ids") or [])
            ch = [c for c in ch if c.get("chunk_id") not in drop]
        fin, reason, it = run_gate(m["field"], m["mutant_value"], ch, m["surnames_ref"])
        m["gate_final"] = fin
        m["gate_reason"] = reason
        m["correct"] = (fin == m["expected"])

    # ---- LLM paraphrase pass ----
    llm_rows = []
    if args.phase in ("llm", "all"):
        for b in base:
            if b["field"] != "results":
                continue
            pv = paraphrase_llm(b["value"])
            row = {"cls": "paraphrase_llm", "expected": "RETURNED", **_slim(b),
                   "mutant_value": pv, "seed": LLM_SEED, "note": ""}
            if pv and not pv.startswith("__LLM_ERROR__"):
                # guard: only a valid paraphrase test if it kept the numbers
                kept = set(_NUMVAL.findall(pv)) >= set(_NUMVAL.findall(b["value"]))
                row["kept_all_numbers"] = kept
                fin, reason, _ = run_gate(b["field"], pv, b["chunks"], b["surnames"])
                row["gate_final"] = fin
                row["gate_reason"] = reason
                row["correct"] = (fin == "RETURNED")
            else:
                row["gate_final"] = "SKIPPED"
                row["error"] = pv
            llm_rows.append(row)

    all_rows = mutants + llm_rows
    (OUT / "mutants.json").write_text(json.dumps(all_rows, indent=2, default=str), encoding="utf-8")

    # ---- special A: two-token cross-row binding ----
    crossrow = _crossrow_probe(base, rng)
    (OUT / "crossrow.json").write_text(json.dumps(crossrow, indent=2, default=str), encoding="utf-8")

    # ---- special B: single-digit anchor exclusion ----
    singled = _single_digit_scan()
    (OUT / "single_digit.json").write_text(json.dumps(singled, indent=2, default=str), encoding="utf-8")

    _summ(base, all_rows, crossrow, singled)


def _slim(b):
    return {"corpus": b["corpus"], "paper_id": b["paper_id"], "field": b["field"],
            "base_value": b["value"], "surnames_ref": b["surnames"]}


def _chunks_for(base, m):
    for b in base:
        if b["paper_id"] == m["paper_id"] and b["corpus"] == m["corpus"]:
            return b["chunks"]
    return []


_ROW_RE = re.compile(r"\b([A-Z][A-Za-z][A-Za-z0-9\-]*(?:[ /][A-Za-z0-9\-]{2,}){0,3})"
                     r"\s+(\d+\.\d+|\d{2,}(?:\.\d+)?)\s+(\d+\.\d+|\d{2,}(?:\.\d+)?)")


def _crossrow_probe(base, rng):
    """Real multi-row result-table chunk: bind row-A's method label + a real
    column-metric token to row-B's number. If the gate RETURNS the crafted claim,
    the >=2-significant-token rule was fooled — the number belongs to another row."""
    out, seen = [], set()
    for b in base:
        for c in b["chunks"]:
            t = c.get("text", "")
            cid = c.get("chunk_id")
            if cid in seen:
                continue
            metrics_here = sorted(_sig_tokens(t) & _METRIC_TOKENS)
            rows = _ROW_RE.findall(t)  # (label, n1, n2)
            # need >=2 rows with clean method-name labels and distinct leading numbers
            clean = [(lbl.strip(), n1) for lbl, n1, _ in rows
                     if 3 <= len(lbl.strip()) <= 28 and not lbl.strip().lower().startswith(("table", "figure", "section", "the ", "we ", "our "))]
            if len(clean) >= 2 and metrics_here:
                (labelA, numA), (labelB, numB) = clean[0], clean[1]
                if numA == numB or not (numB in t):
                    continue
                seen.add(cid)
                metric = metrics_here[0]
                claim = f"{labelA} reports a {metric} of {numB} on the benchmark."
                fin, reason, _ = run_gate("results", claim, b["chunks"], b["surnames"])
                out.append({"corpus": b["corpus"], "paper_id": b["paper_id"], "section": c.get("section"),
                            "row_A_label": labelA, "row_A_number": numA,
                            "row_B_number_used": numB, "metric_token": metric,
                            "crafted_claim": claim, "gate_final": fin, "gate_reason": reason,
                            "FOOLED": fin == "RETURNED",
                            "chunk_excerpt": re.sub(r"\s+", " ", t)[:260]})
            if len(out) >= 30:
                return out
    return out


_SD_UNIT = re.compile(
    r"(?<![\d.])(\d)\s?(?:%|x\b|-?fold\b|(?:percentage )?points?\b|times\b|pp\b)", re.I)
_SD_BYNUM = re.compile(
    r"\b(?:by|of|to|from|reaching|around|about|nearly|only|just|up to|over)\s+(\d)(?![\d.\w])")
_METRICWORD = re.compile(
    r"\b(accuracy|precision|recall|f1|f-?score|dice|iou|auc|bleu|rouge|mae|rmse|mrr|ndcg|"
    r"map|exact match|em|correlation|sensitivity|specificity|score|improv|increas|reduc|gain|"
    r"outperform|higher|lower|better)\b", re.I)


def _single_digit_scan():
    """Count genuine single-digit quantitative result phrasings that `_NUMVAL`
    (>=2 digits or a decimal) can never anchor. Scans the LLM `results` /
    `key_findings` / `inferences` fields AND the paper chunks."""
    caches = [
        HERE / "runs/prodab-20260902T004416Z/canonical/processed/extraction_cache.json",
        ROOT / "data_test/processed/extraction_cache.json",
    ]
    chunkfiles = [
        HERE / "runs/prodab-20260902T004416Z/canonical/processed/chunks.json",
        ROOT / "data_test/processed/chunks.json",
    ]
    hits, papers, scanned = [], set(), 0

    def scan_sentences(text, pid, origin):
        for sent in re.split(r"(?<=[.!?])\s+", text or ""):
            s = sent.strip()
            if len(s) < 15:
                continue
            m = _SD_UNIT.search(s) or (_SD_BYNUM.search(s) if _METRICWORD.search(s) else None)
            if m and not _NUMVAL.search(m.group(0)):
                hits.append({"paper_id": pid[:12], "origin": origin,
                             "match": m.group(0).strip(), "sentence": s[:200]})
                papers.add(pid)

    for cf in caches:
        if not cf.exists():
            continue
        for pid, rec in json.loads(cf.read_text(encoding="utf-8")).items():
            for fld in ("results", "key_findings", "inferences"):
                t = rec.get(fld)
                if isinstance(t, str) and t.strip():
                    if fld == "results":
                        scanned += 1
                    scan_sentences(t, pid, f"extraction.{fld}")
    for cf in chunkfiles:
        if not cf.exists():
            continue
        for c in json.loads(cf.read_text(encoding="utf-8")):
            if c.get("section") in ("results", "discussion", "abstract", "conclusion", "experimental_setup"):
                scan_sentences(c.get("text", ""), c.get("paper_id", ""), "chunk." + str(c.get("section")))

    # dedupe by (paper, match, first 60 chars)
    uniq, seen = [], set()
    for h in hits:
        k = (h["paper_id"], h["match"], h["sentence"][:60])
        if k not in seen:
            seen.add(k)
            uniq.append(h)
    return {"result_fields_scanned": scanned, "single_digit_quant_mentions": len(uniq),
            "distinct_papers": len(papers), "examples": uniq[:40]}


def _summ(base, rows, crossrow, singled):
    by = defaultdict(lambda: Counter())
    for r in rows:
        if r.get("gate_final") in (None, "SKIPPED"):
            by[r["cls"]]["skipped"] += 1
            continue
        by[r["cls"]][r["gate_final"]] += 1
        by[r["cls"]]["correct" if r["correct"] else "WRONG"] += 1

    EXP = {"numeric_perturbation": "ABSTAINED", "fabrication": "ABSTAINED",
           "support_deletion_primary": "ABSTAINED", "support_deletion_full": "ABSTAINED",
           "paraphrase_rule": "RETURNED", "paraphrase_llm": "RETURNED"}
    print("\n=== MUTANT COUNTS / VERDICTS ===")
    for cls, c in by.items():
        exp = EXP.get(cls, "?")
        n = c["correct"] + c["WRONG"]
        print(f"  {cls:22} n={n:3}  expected={exp:9}  correct={c['correct']:3}  WRONG={c['WRONG']:3}  "
              f"(RETURNED={c['RETURNED']}, ABSTAINED={c['ABSTAINED']}, skipped={c['skipped']})")

    # confusion matrix: positives = paraphrases (should ACCEPT); negatives = pert/fab/del
    pos = [r for r in rows if r["cls"].startswith("paraphrase") and r.get("gate_final") not in (None, "SKIPPED")]
    neg = [r for r in rows if r["cls"] in ("numeric_perturbation", "fabrication",
                                           "support_deletion_primary", "support_deletion_full")]
    TP = sum(1 for r in pos if r["gate_final"] == "RETURNED")
    FN = sum(1 for r in pos if r["gate_final"] == "ABSTAINED")
    FP = sum(1 for r in neg if r["gate_final"] == "RETURNED")
    TN = sum(1 for r in neg if r["gate_final"] == "ABSTAINED")
    prec = TP / (TP + FP) if TP + FP else None
    rec = TP / (TP + FN) if TP + FN else None
    spec = TN / (TN + FP) if TN + FP else None
    print("\n=== CONFUSION MATRIX (synthetic ground truth) ===")
    print(f"  should-ACCEPT (paraphrase): TP={TP}  FN={FN}")
    print(f"  should-REJECT (pert/fab/del): FP={FP}  TN={TN}")
    print(f"  precision={prec}  recall/sensitivity={rec}  specificity={spec}")

    for cls in ("paraphrase_rule", "paraphrase_llm"):
        sub = [r for r in rows if r["cls"] == cls and r.get("gate_final") not in (None, "SKIPPED")]
        p = sum(1 for r in sub if r["gate_final"] == "RETURNED")
        print(f"\n  {cls} pass rate: {p}/{len(sub)}" + (f"  (seed {LLM_SEED})" if cls.endswith('llm') else ""))
        for r in sub:
            if r["gate_final"] != "RETURNED":
                print(f"    FALSE NEGATIVE [{r['paper_id'][:10]}] reason={r['gate_reason']!r}")
                print(f"       base : {r['base_value'][:110]!r}")
                print(f"       mutant: {str(r['mutant_value'])[:110]!r}")

    fooled = [x for x in crossrow if x["FOOLED"]]
    print(f"\n=== TWO-TOKEN CROSS-ROW BINDING ===  probes={len(crossrow)}  FOOLED={len(fooled)}")
    for x in fooled[:10]:
        print(f"  [{x['paper_id'][:10]}] used row-B number {x['row_B_number_used']} with '{x['row_A_label']}' + '{x['metric_token']}' -> RETURNED")
        print(f"     claim: {x['crafted_claim']}")

    print(f"\n=== SINGLE-DIGIT ANCHOR EXCLUSION ===")
    print(f"  result fields scanned: {singled['result_fields_scanned']}")
    print(f"  single-digit quantitative mentions (unreachable by _NUMVAL): {singled['single_digit_quant_mentions']} "
          f"across {singled['distinct_papers']} papers")
    for e in singled["examples"][:8]:
        print(f"    [{e['paper_id']}] {e['match']!r}  ::  {e['sentence'][:120]!r}")
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
