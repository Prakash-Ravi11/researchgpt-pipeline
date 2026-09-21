"""PHASE 3 step 2 — attach verification fields, emit Prakash's labelling worksheet,
and compute the (machine-labelled, unvalidated) distribution plus section B.

Reads the fixed-seed samples written by phase3_sample.py and the delivery flags
measured by phase2_ladder.py. Does NOT re-run any retrieval and does NOT
reimplement the cell-C measurement -- phase2_ladder is imported and its
per_anchor.json output is consumed as the measurement of record.

Writes only into runs/phase3_composition/.

The suggested labels below are MACHINE-ASSISTED, UNVALIDATED. They were produced
by Claude Opus 5 reading each anchor's +/-220-char window and the paper title.
No classifier was built and no separate LLM call was made. Authority over the
final labels rests with Prakash (RESEARCH_DIRECTIVE.md, "Labelling authority").
"""
from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent.parent))

import phase2_ladder  # noqa: E402  -- reuse, do not reimplement the measurement

OUT = HERE / "runs" / "phase3_composition"
P2 = HERE / "runs" / "phase2_ladder" / "per_anchor.json"
CHUNKS = HERE / "runs" / "prodab-20260902T004416Z" / "canonical" / "processed" / "chunks.json"

# ---- suggested labels (machine-assisted, unvalidated) -----------------------
SUGGEST_UNNAMED = {
    "HAS_NAME_MISSED": "U06 U07 U25 U29 U32 U40 U44 U45 U46 U54 U58".split(),
    "NAMEABLE_INDIRECT": ("U08 U14 U17 U18 U19 U22 U23 U24 U34 U41 U42 U47 U48 "
                          "U50 U51 U53 U56 U57 U59").split(),
    "GENUINELY_UNNAMEABLE": "U01 U03 U04 U05 U09 U12 U13 U21 U30 U31 U39 U49 U60".split(),
    "MALFORMED": ("U02 U10 U11 U15 U16 U20 U26 U27 U28 U33 U35 U36 U37 U38 "
                  "U43 U52 U55").split(),
}
SUGGEST_NAMED_CORRECT = "N02 N04 N06 N10 N12 N16 N22 N24 N28".split()

# the quoted name, for HAS_NAME_MISSED (directive: "Quote the name")
QUOTED_NAME = {
    "U06": "ArSQUAD", "U07": "BioASQ / NQ", "U25": "RepliQA / SQuAD2",
    "U29": "beta values (beta1, beta2)", "U32": "BioASQ / NQ",
    "U40": "FinanceBench / ConvFinQA", "U44": "NQ / HotpotQA / BioASQ",
    "U45": "accuracy  [broken by line-hyphenation as 'accu- racy']",
    "U46": "CLAPNQ / FiQA", "U54": "SaudiWiki / QA4MRE / Hindawi",
    "U58": "StackExchange / Wikipedia-DPR",
}

# verification_method / verification_confidence per the directive's enums.
VERIF_OVERRIDE = {
    "U45": ("normalized", "high"),   # matches the frozen regex only after de-hyphenation
    "U29": ("semantic", "medium"),   # named hyperparameter, not a metric/dataset
    "U19": ("semantic", "low"),      # "Somewhat similar" is a rating category
    "U50": ("semantic", "low"),      # "External context" row, columns unnamed
    "N14": ("exact", "high"),        # regex matched Portuguese "em"; verbatim check
    "N06": ("structural", "high"),   # value sits under the mAP@0.5 column
    "N07": ("structural", "medium"), "N17": ("structural", "medium"),
    "N19": ("structural", "medium"), "N21": ("structural", "medium"),
}
BUCKET_VERIF = {
    "HAS_NAME_MISSED": ("exact", "high"),        # the name string is present verbatim
    "NAMEABLE_INDIRECT": ("semantic", "medium"),  # judgement that a human could name it
    "GENUINELY_UNNAMEABLE": ("structural", "high"),  # reference-list position
    "MALFORMED": ("structural", "high"),         # value absent, or a structure/id artifact
}
# C5: could someone write a usable query from anchor text + title alone?
CEILING_USABLE = set(SUGGEST_UNNAMED["HAS_NAME_MISSED"]) | set(SUGGEST_UNNAMED["NAMEABLE_INDIRECT"])


def main() -> None:
    su = json.loads((OUT / "sample_unnamed.json").read_text(encoding="utf-8"))
    sn = json.loads((OUT / "sample_named.json").read_text(encoding="utf-8"))
    rows = json.loads(P2.read_text(encoding="utf-8"))
    chunks = json.loads(CHUNKS.read_text(encoding="utf-8"))
    title_of = {c["paper_id"]: (c.get("title") or "") for c in chunks}

    lab = {sid: b for b, ids in SUGGEST_UNNAMED.items() for sid in ids}
    assert len(lab) == 60, f"expected 60 suggested labels, got {len(lab)}"

    for r in su:
        sid = r["sample_id"]
        r["suggested_label"] = lab[sid]
        vm, vc = VERIF_OVERRIDE.get(sid, BUCKET_VERIF[lab[sid]])
        r["verification_method"], r["verification_confidence"] = vm, vc
        r["quoted_name"] = QUOTED_NAME.get(sid)
        r["ceiling_usable_machine_est"] = sid in CEILING_USABLE
    for r in sn:
        sid = r["sample_id"]
        r["suggested_label"] = "CORRECT" if sid in SUGGEST_NAMED_CORRECT else "FALSE_POSITIVE"
        default = ("exact", "high") if sid in SUGGEST_NAMED_CORRECT else ("semantic", "medium")
        if not r["value_located_in_chunk"]:
            default = ("structural", "high")
        vm, vc = VERIF_OVERRIDE.get(sid, default)
        r["verification_method"], r["verification_confidence"] = vm, vc

    # ---- section B: reuse phase2_ladder's measured flags, do not re-measure ----
    long_rows = [x for x in rows if not x["paper_is_short"]]
    named = [x for x in long_rows if x["field_query"] != title_of.get(x["paper_id"], "")]
    unnamed = [x for x in long_rows if x["field_query"] == title_of.get(x["paper_id"], "")]

    def cell_c(subset):
        """Same statistic as phase2_ladder.summarise for cell C: delivery, the
        uniform-random null at that budget, and the ratio. Flags come from
        phase2_ladder's run; nothing is retrieved again here."""
        if not subset:
            return None
        k = phase2_ladder.N_SMALL
        rate = sum(x["C"] for x in subset) / len(subset)
        null = sum(min(k, x["n_chunks"]) / x["n_chunks"] for x in subset) / len(subset)
        return {"n": len(subset), "delivery": round(rate, 4), "null": round(null, 4),
                "ratio_to_random": round(rate / null, 3) if null else None}

    b3 = {"NAMED": cell_c(named), "UNNAMED": cell_c(unnamed)}

    by_sec, by_loc = defaultdict(list), defaultdict(list)
    for x in unnamed:
        by_sec[x["section"][:28]].append(x)
        by_loc[x["location"]].append(x)
    b4 = {"by_section": {k: cell_c(v) for k, v in by_sec.items() if len(v) >= 40},
          "by_location": {k: cell_c(v) for k, v in by_loc.items()}}

    dist = Counter(lab.values())
    named_dist = Counter(r["suggested_label"] for r in sn)
    notloc = sum(1 for r in sn if not r["value_located_in_chunk"])
    fp_loc = sum(1 for r in sn
                 if r["suggested_label"] == "FALSE_POSITIVE" and r["value_located_in_chunk"])
    ceiling = sum(1 for r in su if r["ceiling_usable_machine_est"])

    summary = {
        "provenance": "machine-labelled, unvalidated — suggested by Claude Opus 5; "
                      "authority rests with Prakash",
        "pilot": "n=60 unnamed / n=30 named; every bucket is below the 50-per-category "
                 "kappa threshold, so this is a pilot by construction (pilot, n<50)",
        "unnamed_distribution": dict(dist),
        "named_distribution": dict(named_dist),
        "named_value_not_locatable": notloc,
        "named_fp_excluding_unlocatable": {"n": 30 - notloc, "fp": fp_loc,
                                           "rate": round(fp_loc / (30 - notloc), 4)},
        "ceiling_usable_of_60": ceiling,
        "verification_method_counts": dict(Counter(
            r["verification_method"] for r in su + sn)),
        "verification_confidence_counts": dict(Counter(
            r["verification_confidence"] for r in su + sn)),
        "B3": b3, "B4": b4,
    }
    (OUT / "suggested_labels.json").write_text(
        json.dumps({"unnamed": su, "named": sn}, indent=1), encoding="utf-8")
    (OUT / "summary.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")

    # ---- Prakash's worksheet -------------------------------------------------
    w = ["# Phase 3 — labelling worksheet",
         "",
         "**These 90 labels are Prakash's to make.** The `SUGGESTED` line on each item is",
         "**machine-assisted and unvalidated** (Claude Opus 5, by reading the window below —",
         "no classifier, no separate LLM call). Write your label in `YOUR LABEL:`. Where you",
         "disagree, your label is the one that counts.",
         "",
         f"Seed 42 · {len(su)} unnamed + {len(sn)} named · every bucket is under the 50-item",
         "kappa threshold, so this is a **pilot (n<50)**: report raw agreement, not kappa.",
         "",
         "---",
         "",
         "## C5 CEILING — needs your confirmation",
         "",
         f"Machine estimate: **{ceiling} of 60 ({ceiling / 60:.1%})** anchors could be given a",
         "usable retrieval query by someone reading only the anchor text and the paper title,",
         "with no access to the answer location. Each item below carries",
         "`CEILING(machine-est)`. **Please confirm or correct this count.**",
         "",
         "---",
         "",
         "## A1 — 60 UNNAMED anchors",
         "",
         "Buckets: HAS_NAME_MISSED · NAMEABLE_INDIRECT · GENUINELY_UNNAMEABLE · MALFORMED",
         ""]
    for r in su:
        win = " ".join(r["window"].split())[:300]
        loc = "" if r["value_located_in_chunk"] else "  ⚠ value NOT locatable in its chunk"
        w += [f"### {r['sample_id']} · value `{r['value']}` · {r['section'][:26]}/{r['location']}{loc}",
              f"- paper: `{r['paper_id']}`",
              f"- title: *{r['title'][:95]}*",
              f"- window: > {win}",
              f"- SUGGESTED (machine-assisted, unvalidated): **{r['suggested_label']}**"
              + (f" — name quoted: `{r['quoted_name']}`" if r.get("quoted_name") else ""),
              f"- verification_method: `{r['verification_method']}` · "
              f"verification_confidence: `{r['verification_confidence']}`",
              f"- CEILING(machine-est): {'usable' if r['ceiling_usable_machine_est'] else 'not usable'}",
              "- **YOUR LABEL:** ________________  **YOUR CEILING CALL:** ________",
              ""]
    w += ["---", "", "## A2 — 30 NAMED anchors (is the extractor right when it fires?)", "",
          "Buckets: CORRECT · FALSE_POSITIVE", ""]
    for r in sn:
        win = " ".join(r["window"].split())[:260]
        loc = "" if r["value_located_in_chunk"] else "  ⚠ value NOT locatable in its chunk"
        w += [f"### {r['sample_id']} · value `{r['value']}` · matched `{r['metric_found']}` · "
              f"{r['section'][:24]}/{r['location']}{loc}",
              f"- paper: `{r['paper_id']}`",
              f"- window: > {win}",
              f"- SUGGESTED (machine-assisted, unvalidated): **{r['suggested_label']}**",
              f"- verification_method: `{r['verification_method']}` · "
              f"verification_confidence: `{r['verification_confidence']}`",
              "- **YOUR LABEL:** ________________",
              ""]
    (OUT / "labelling_sheet.md").write_text("\n".join(w), encoding="utf-8")

    print(json.dumps(summary, indent=1)[:2000])
    print(f"\nworksheet -> {OUT / 'labelling_sheet.md'}")


if __name__ == "__main__":
    main()
