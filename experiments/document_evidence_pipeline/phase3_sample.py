"""PHASE 3 — sample anchors for hand classification of the field-name extractor's misses.

Measurement only. src/ is read-only (imported for the frozen metric regex via
retrieval_recall). Does not modify the extractor, does not build a replacement.

Partitions the 3,900 long-paper anchors by whether the frozen _METRIC regex
(retrieval_recall.py:41-45) fires in the +/-220-char window around the anchor
value -- the exact NAMED/UNNAMED split Phase 2 used -- then draws a fixed-seed
random sample of each for classification by reading.

Writes runs/phase3_composition/{sample_unnamed.json, sample_named.json, split.json}.
"""
from __future__ import annotations

import json
import random
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(ROOT))

RUN = HERE / "runs" / "prodab-20260902T004416Z" / "canonical"
CHUNKS = RUN / "processed" / "chunks.json"
ANCHORS = HERE / "runs" / "retrieval_recall" / "anchors.json"
PHASE2 = HERE / "runs" / "phase2_ladder" / "per_anchor.json"
OUT = HERE / "runs" / "phase3_composition"

SEED = 42
N_UNNAMED, N_NAMED = 60, 30
WINDOW = 220


def main() -> None:
    from retrieval_recall import _METRIC

    OUT.mkdir(parents=True, exist_ok=True)
    anchors = json.loads(ANCHORS.read_text(encoding="utf-8"))
    chunks = json.loads(CHUNKS.read_text(encoding="utf-8"))
    by_id = {c["chunk_id"]: c for c in chunks}
    title_of = {c["paper_id"]: c.get("title") or "" for c in chunks}
    p2 = {(r["paper_id"], r["value"], r["section"]): r
          for r in json.loads(PHASE2.read_text(encoding="utf-8"))}

    named, unnamed = [], []
    for a in anchors:
        if a["paper_is_short"]:
            continue
        tgt = by_id.get(a["target_chunk"])
        txt = tgt["text"] if tgt else ""
        i = txt.find(a["value"])
        win = txt[max(0, i - WINDOW): i + WINDOW] if i >= 0 else txt[: 2 * WINDOW]
        m = _METRIC.search(win)
        rec = {
            "paper_id": a["paper_id"], "value": a["value"], "section": a["section"],
            "location": a["location"], "n_chunks": a["n_chunks"],
            "target_chunk": a["target_chunk"],
            "title": title_of.get(a["paper_id"], ""),
            "window": win,
            "chunk_text": txt,
            "metric_found": m.group(0) if m else None,
            "value_located_in_chunk": i >= 0,
        }
        key = (a["paper_id"], a["value"], a["section"])
        r2 = p2.get(key)
        if r2:
            rec["cellC"] = r2["C"]
            rec["cellD"] = r2["D"]
            rec["cellA"] = r2["A"]
        (named if m else unnamed).append(rec)

    split = {"long_anchors": len(named) + len(unnamed),
             "named": len(named), "unnamed": len(unnamed),
             "unnamed_frac": round(len(unnamed) / (len(named) + len(unnamed)), 4),
             "value_not_locatable_in_chunk": sum(
                 1 for r in named + unnamed if not r["value_located_in_chunk"])}
    print(json.dumps(split, indent=1))

    rng = random.Random(SEED)
    su = rng.sample(unnamed, N_UNNAMED)
    sn = rng.sample(named, N_NAMED)
    for i, r in enumerate(su, 1):
        r["sample_id"] = f"U{i:02d}"
    for i, r in enumerate(sn, 1):
        r["sample_id"] = f"N{i:02d}"

    (OUT / "split.json").write_text(json.dumps(split, indent=1), encoding="utf-8")
    (OUT / "sample_unnamed.json").write_text(json.dumps(su, indent=1), encoding="utf-8")
    (OUT / "sample_named.json").write_text(json.dumps(sn, indent=1), encoding="utf-8")
    print(f"wrote {N_UNNAMED} unnamed + {N_NAMED} named samples (seed {SEED}) to {OUT}")


if __name__ == "__main__":
    main()
