"""PHASE 4 — denominator reconciliation.

Ground truth is Prakash's 85 binary labels, parsed by phase4_step0.py from
human_audit.md. No provisional label, judge output or Phase 3 suggestion is used as
a substitute for a human label anywhere in this file.

The MALFORMED detector below is derived from the Task A labels by inspection of the
structural context of the N-labelled items. Rules only: no model, no LLM, no learned
or tuned threshold. It is scored once. No rule is adjusted after seeing the score.

Delivery flags are phase2_ladder.py's measured output, consumed not reimplemented.
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent.parent))

import phase2_ladder  # noqa: E402  -- reuse of the Phase 2 measurement

RUN = HERE / "runs" / "prodab-20260902T004416Z" / "canonical"
CHUNKS = RUN / "processed" / "chunks.json"
ANCHORS = HERE / "runs" / "retrieval_recall" / "anchors.json"
P2 = HERE / "runs" / "phase2_ladder" / "per_anchor.json"
LADDER = HERE / "runs" / "phase2_ladder" / "ladder.json"
ROUTING = HERE / "runs" / "phase3_label_assist" / "routing.json"
JUDG = HERE / "runs" / "phase3_label_assist" / "judgments.json"
SAMPLE_U = HERE / "runs" / "phase3_composition" / "sample_unnamed.json"
SAMPLE_N = HERE / "runs" / "phase3_composition" / "sample_named.json"
OUT = HERE / "runs" / "phase4_denominator"
WINDOW = 220

# ---------------------------------------------------------------- detector ----
_CITE_NUMERALS = [
    re.compile(r"\bpp?\.\s*(\d+)\s*[–—-]\s*(\d+)"),
    re.compile(r"\bpages?\s+(\d+)\s*[–—-]\s*(\d+)"),
    re.compile(r"\b(\d+)\((\d+)\):(\d+)"),
    re.compile(r"\b(\d+):(\d+)\s*[–—-]\s*(\d+)"),
    re.compile(r"\bvol(?:ume)?\.?\s+(\d+)"),
    re.compile(r"'(\d{2})\b"),
]
_BIB_MARK = re.compile(
    r"\bpp?\.\s*\d+|\bpages?\s+\d+|\bIn:?\s+Proceed|\b\(eds\.\)|arXiv:\d{4}\.\d{4,5}"
    r"|\bURL\s+https?://|\b\d+\(\d+\):\d+|\b\d+:\d+\s*[–—-]\s*\d+", re.I)
_LICENCE = re.compile(r"licen[sc]ed under|Creative Commons", re.I)


def detect(value: str, window: str, located: bool) -> list[str]:
    """Return the MALFORMED rules that fire. Empty list == not malformed."""
    w = " ".join(window.split())
    fired = []

    # M1 -- the value is a citation numeral inside a bibliography entry
    if _BIB_MARK.search(w):
        nums = set()
        for rx in _CITE_NUMERALS:
            for m in rx.finditer(w):
                nums.update(g for g in m.groups() if g)
        if value in nums:
            fired.append("M1_CITATION_NUMERAL")

    # M2 -- the value is a section/heading number or a cross-reference to one
    if re.match(rf"^{re.escape(value)}\.?\s+[A-Z]", w):
        fired.append("M2_SECTION_NUMBER")
    elif re.match(r"^\d+(?:\.\d+)*\.?\s+[A-Z]", w) and \
            re.search(rf"\b{re.escape(value)}\s+[A-Z][a-z]", w):
        fired.append("M2_SECTION_NUMBER")
    elif re.search(r"\d\.\d", value) and re.search(rf"\bin\s+{re.escape(value)}\b", w):
        fired.append("M2_SECTION_NUMBER")

    # M3 -- the value is a numbered pseudocode/algorithm line label
    if re.search(rf"(?:^|\s){re.escape(value)}:\s+[A-Z]", w):
        fired.append("M3_PSEUDOCODE_LINE")

    # M4 -- every occurrence of the value is a sub-token of a longer number
    occ = [m.start() for m in re.finditer(re.escape(value), w)]
    if occ:
        def sub(i: int) -> bool:
            before, after = w[:i], w[i + len(value):]
            return bool(re.search(r"\d[,.]?$", before) or re.match(r"\d", after))
        if all(sub(i) for i in occ):
            fired.append("M4_SUBTOKEN_OF_LONGER_NUMBER")

    # M5 -- the value does not occur in its own target chunk
    if not located:
        fired.append("M5_VALUE_NOT_IN_TARGET_CHUNK")

    # M6 -- the value is a licence version
    if _LICENCE.search(w) and re.fullmatch(r"\d+\.\d+", value):
        fired.append("M6_LICENCE_VERSION")

    return fired


def window_of(rec: dict, by_id: dict) -> tuple[str, bool]:
    tgt = by_id.get(rec["target_chunk"])
    txt = tgt["text"] if tgt else ""
    i = txt.find(rec["value"])
    if i >= 0:
        return txt[max(0, i - WINDOW): i + WINDOW], True
    return txt[: 2 * WINDOW], False


def rate(sub, key):
    return sum(x[key] for x in sub) / len(sub) if sub else None


def null_k(sub, k):
    return sum(min(k, x["n_chunks"]) / x["n_chunks"] for x in sub) / len(sub) if sub else None


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    human = json.loads((OUT / "human_labels.json").read_text(encoding="utf-8"))
    chunks = json.loads(CHUNKS.read_text(encoding="utf-8"))
    by_id = {c["chunk_id"]: c for c in chunks}
    su = {r["sample_id"]: r for r in json.loads(SAMPLE_U.read_text(encoding="utf-8"))}
    sn = {r["sample_id"]: r for r in json.loads(SAMPLE_N.read_text(encoding="utf-8"))}
    routing = {r["id"]: r for r in json.loads(ROUTING.read_text(encoding="utf-8"))["items"]}
    judg = {r["id"]: r for r in json.loads(JUDG.read_text(encoding="utf-8"))["items"]}

    res = {}

    # ---- A. agreement diagnostics -------------------------------------------
    a1 = {}
    for f in ("framing_1", "framing_2"):
        agree = dis = unc = 0
        for sid, hv in human.items():
            jv = judg[sid][f]["answer"]
            if jv == "UNCERTAIN":
                unc += 1
                dis += 1
            elif jv == hv:
                agree += 1
            else:
                dis += 1
        n = len(human)
        a1[f] = {"comparable_n": n, "agreements": agree, "disagreements": dis,
                 "of_which_source_UNCERTAIN": unc, "raw_agreement": round(agree / n, 4),
                 "excluded_no_source_label": 0}
    prov_n = [i for i, r in routing.items() if r["route"] == "PROVISIONAL_N"]
    overlap = sorted(set(prov_n) & set(human))
    a2 = {"provisional_N_ids": sorted(prov_n), "labelled_by_human": overlap,
          "overlap_n": len(overlap)}
    if len(overlap) <= 2:
        a2["note"] = ("overlap too small to support a rate; reporting the observation(s) "
                      "only, no percentage computed")
        a2["observations"] = {i: {"human": human[i], "provisional": routing[i]["provisional_label"],
                                  "rules_fired": routing[i]["rules_fired"]} for i in overlap}
    dis_ids = [i for i, r in routing.items() if r["framing_1"] != r["framing_2"]]
    agr_ids = [i for i, r in routing.items() if r["framing_1"] == r["framing_2"]]
    a3 = {"framing_disagreement_group": {"n_total": len(dis_ids),
                                         "n_human_labelled": len([i for i in dis_ids if i in human]),
                                         "human_split": dict(Counter(human[i] for i in dis_ids if i in human))},
          "framing_agreement_group": {"n_total": len(agr_ids),
                                      "n_human_labelled": len([i for i in agr_ids if i in human]),
                                      "human_split": dict(Counter(human[i] for i in agr_ids if i in human))}}
    a4 = {"id": "U52", "human_label": human.get("U52"),
          "routing": {k: routing["U52"][k] for k in
                      ("deterministic_status", "rules_fired", "framing_1", "framing_2",
                       "route", "provisional_label", "in_blind_audit_sample")},
          "framing_1_reason": judg["U52"]["framing_1"]["reason"],
          "framing_2_reason": judg["U52"]["framing_2"]["reason"],
          "status": "single observation, n=1, NOT an audit; not generalised"}
    res["A"] = {"A1": a1, "A2": a2, "A3": a3, "A4": a4}

    # ---- B1/B2 score the detector on the human Task A labels -----------------
    task_a = {k: v for k, v in human.items() if k.startswith("U")}
    tp = fp = fn = tn = 0
    per_item = {}
    for sid, hv in task_a.items():
        r = su[sid]
        win, loc = window_of(r, by_id)
        fired = detect(r["value"], win, loc)
        pred = "N" if fired else "Y"
        per_item[sid] = {"human": hv, "predicted": pred, "rules_fired": fired}
        if hv == "N" and pred == "N":
            tp += 1
        elif hv == "Y" and pred == "N":
            fp += 1
        elif hv == "N" and pred == "Y":
            fn += 1
        else:
            tn += 1
    prec = tp / (tp + fp) if tp + fp else None
    rec_ = tp / (tp + fn) if tp + fn else None
    res["B"] = {"B2": {"n_scored": len(task_a), "TP": tp, "FP": fp, "FN": fn, "TN": tn,
                       "precision": round(prec, 4) if prec is not None else None,
                       "recall": round(rec_, 4) if rec_ is not None else None,
                       "false_positives": [k for k, v in per_item.items()
                                           if v["human"] == "Y" and v["predicted"] == "N"],
                       "false_negatives": [k for k, v in per_item.items()
                                           if v["human"] == "N" and v["predicted"] == "Y"]},
                "per_item": per_item}
    (OUT / "detector_scoring.json").write_text(json.dumps(res["B"], indent=1), encoding="utf-8")
    print(f"B2  n={len(task_a)} TP={tp} FP={fp} FN={fn} TN={tn} "
          f"precision={prec:.4f} recall={rec_:.4f}")

    gate_pass = prec is not None and prec >= 0.80
    res["B"]["B3_gate"] = {"threshold": 0.80, "precision": round(prec, 4),
                           "passed": gate_pass}
    print(f"B3  GATE {'PASS' if gate_pass else 'FAIL'} (precision {prec:.4f} vs 0.80)")

    if gate_pass:
        # ---- B4 apply corpus-wide ------------------------------------------
        anchors = json.loads(ANCHORS.read_text(encoding="utf-8"))
        longa = [a for a in anchors if not a["paper_is_short"]]
        flags = {}
        for a in longa:
            win, loc = window_of(a, by_id)
            flags[(a["paper_id"], a["value"], a["section"])] = bool(detect(a["value"], win, loc))
        nmal = sum(1 for v in flags.values() if v)
        res["B"]["B4"] = {"total_long_anchors": len(longa), "MALFORMED": nmal,
                          "non_MALFORMED": len(longa) - nmal,
                          "fraction": round(nmal / len(longa), 4),
                          "numerator": nmal, "denominator": len(longa)}
        print(f"B4  {nmal}/{len(longa)} = {nmal/len(longa):.4f} MALFORMED")

        # ---- B5 restate ------------------------------------------------------
        rows = json.loads(P2.read_text(encoding="utf-8"))
        lrows = [x for x in rows if not x["paper_is_short"]]
        keyed = {(x["paper_id"], x["value"], x["section"]): x for x in lrows}
        for k, x in keyed.items():
            x["_malformed"] = flags.get(k, False)
        clean = [x for x in lrows if not x.get("_malformed")]
        amap = {(a["paper_id"], a["value"], a["section"]): a for a in longa}
        for x in lrows:
            a = amap.get((x["paper_id"], x["value"], x["section"]))
            x["_r10"] = bool(a and ((a["rank_r1"] or 10**9) <= 10
                                    or (a["best_alt_rank_r1"] or 10**9) <= 10))
        cleanr = [x for x in lrows if not x.get("_malformed")]

        K = {"A": None, "B": None, "C": phase2_ladder.N_SMALL, "D": phase2_ladder.N_BIG, "E": 10}
        cells = {}
        for c in "ABCDE":
            old_d, new_d = rate(lrows, c), rate(cleanr, c)
            row = {"old_delivery": round(old_d, 4), "cleaned_delivery": round(new_d, 4),
                   "change": round(new_d - old_d, 4),
                   "old_n": len(lrows), "cleaned_n": len(cleanr)}
            if K[c] is None:
                row["ratio_to_random"] = ("NOT RECOMPUTABLE — the per-paper union size that "
                                          "defines this cell's budget was not persisted by "
                                          "phase2_ladder.py; only its mean survives in ladder.json")
            else:
                on, nn = null_k(lrows, K[c]), null_k(cleanr, K[c])
                row["old_ratio_to_random"] = round(old_d / on, 3)
                row["cleaned_ratio_to_random"] = round(new_d / nn, 3)
                row["ratio_change"] = round(new_d / nn - old_d / on, 3)
            cells[c] = row
        r10_old, r10_new = rate(lrows, "_r10"), rate(cleanr, "_r10")
        sec = {}
        unnamed_old = [x for x in lrows if x["field_query"] ==
                       {c["paper_id"]: (c.get("title") or "") for c in chunks}.get(x["paper_id"], "")]
        unnamed_new = [x for x in unnamed_old if not x.get("_malformed")]
        for name in ("results", "references", "conclusion", "discussion"):
            o = [x for x in unnamed_old if x["section"][:28] == name]
            n_ = [x for x in unnamed_new if x["section"][:28] == name]
            e = {"old_n": len(o), "cleaned_n": len(n_)}
            if o:
                e["old_ratio"] = round(rate(o, "C") / null_k(o, 3), 3)
            e["cleaned_ratio"] = round(rate(n_, "C") / null_k(n_, 3), 3) if n_ else None
            sec[name] = e
        for loc in ("prose", "table"):
            o = [x for x in unnamed_old if x["location"] == loc]
            n_ = [x for x in unnamed_new if x["location"] == loc]
            sec[loc] = {"old_n": len(o), "cleaned_n": len(n_),
                        "old_ratio": round(rate(o, "C") / null_k(o, 3), 3) if o else None,
                        "cleaned_ratio": round(rate(n_, "C") / null_k(n_, 3), 3) if n_ else None}
        res["B"]["B5"] = {"cells": cells,
                          "R_at_10": {"old": round(r10_old, 4), "cleaned": round(r10_new, 4),
                                      "change": round(r10_new - r10_old, 4)},
                          "phase3_B4_sections": sec}
        print("B5  cells:", {c: (cells[c]["old_delivery"], cells[c]["cleaned_delivery"]) for c in "ABCDE"})
        print(f"B5  R@10 {r10_old:.4f} -> {r10_new:.4f}")

    # ---- C binding -----------------------------------------------------------
    task_b = {k: v for k, v in human.items() if k.startswith("N")}
    unloc = [k for k in task_b if not sn[k]["value_located_in_chunk"]]
    c_correct = [k for k, v in task_b.items() if v == "Y"]
    c_wrong = [k for k, v in task_b.items() if v == "N"]
    wrong_loc = [k for k in c_wrong if k not in unloc]
    res["C"] = {"n_task_B": len(task_b), "fires_correct": len(c_correct),
                "fires_wrong": len(c_wrong), "unlocatable_ids": unloc,
                "unlocatable_n": len(unloc),
                "unlocatable_human_labels": {k: task_b[k] for k in unloc},
                "wrong_rate_all": round(len(c_wrong) / len(task_b), 4),
                "wrong_rate_excluding_unlocatable": round(len(wrong_loc) / (len(task_b) - len(unloc)), 4),
                "n_excluding_unlocatable": len(task_b) - len(unloc)}
    print(f"C   wrong {len(c_wrong)}/{len(task_b)}; excl unlocatable "
          f"{len(wrong_loc)}/{len(task_b)-len(unloc)}")

    (OUT / "phase4_results.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
    print("\nwrote", OUT / "phase4_results.json")


if __name__ == "__main__":
    main()
