"""Neutrality check for the anchor-rule centralization (src/evidence/anchors.py).

Over the 34-paper canonical corpus, for EVERY chunk, compares the centralized
`find_anchors` (imported by the gate and both harnesses) against an inline
verbatim copy of the pre-centralization `anchors_in_text` / `is_anchor` from
retrieval_recall.py.  Per-paper counts, before vs after.  No GPU / no model.

The full Test-3 count (3981) is confirmed separately by re-running
retrieval_recall.py itself (only its imports changed, so if the per-chunk anchor
sets are identical the 3981 is identical by construction).

  python experiments/document_evidence_pipeline/anchor_neutrality_check.py
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import retrieval_recall as R  # noqa: E402  (uses the centralized anchors_in_text / _NUMVAL)

# ---- inline verbatim copy of the PRE-centralization implementation -----------
_OLD_NUMVAL = re.compile(r"\d+\.\d+|\b\d{2,}\b")
_OLD_YEAR = re.compile(r"^(19|20)\d{2}$")
_OLD_EXCLUDE_PREFIX = re.compile(
    r"(section|sec\.?|equation|eq\.?|figure|fig\.?|table|tab\.?|appendix|"
    r"chapter|line|step|version|v)\s*$", re.I)


def _old_is_anchor(value, before, inside_brackets):
    if _OLD_YEAR.match(value):
        return False
    if inside_brackets:
        return False
    if _OLD_EXCLUDE_PREFIX.search(before[-14:]):
        return False
    if re.search(r"\d{4}\.\d{4,5}$", before + value):
        return False
    return True


def _old_anchors_in_text(text):
    out = []
    for m in _OLD_NUMVAL.finditer(text):
        s = m.start()
        before = text[max(0, s - 20):s]
        lb, rb = text.rfind("[", 0, s), text.rfind("]", 0, s)
        if _old_is_anchor(m.group(0), before, lb > rb):
            out.append((m.group(0), s))
    return out


def main() -> None:
    chunks = json.loads(R.CHUNKS.read_text(encoding="utf-8"))

    by_paper: dict[str, list[dict]] = defaultdict(list)
    for c in chunks:
        if c.get("has_full_text"):
            by_paper[c["paper_id"]].append(c)
    for pid in by_paper:
        by_paper[pid].sort(key=lambda c: c["chunk_index"])

    # (a) raw per-chunk equality: new vs old
    raw_new = Counter()
    raw_old = Counter()
    mismatch_chunks = 0
    for pid, pcs in by_paper.items():
        for c in pcs:
            n = R.anchors_in_text(c["text"])
            o = _old_anchors_in_text(c["text"])
            raw_new[pid] += len(n)
            raw_old[pid] += len(o)
            if n != o:
                mismatch_chunks += 1

    # ---- report ----
    print(f"papers: {len(by_paper)}   chunks: {sum(len(v) for v in by_paper.values())}")
    print(f"raw anchors_in_text  new==old per chunk: "
          f"{'YES (all chunks)' if mismatch_chunks == 0 else f'NO — {mismatch_chunks} chunks differ'}"
          f"   new_total={sum(raw_new.values())}  old_total={sum(raw_old.values())}")
    print(f"\n{'paper_id':16} before  after")
    for pid in sorted(by_paper):
        flag = "" if raw_new[pid] == raw_old[pid] else "   <-- DIFF"
        print(f"{pid[:16]:16} {raw_old[pid]:>6}  {raw_new[pid]:>5}{flag}")

    ok = (mismatch_chunks == 0 and sum(raw_new.values()) == sum(raw_old.values()))
    print(f"\nRAW-RULE NEUTRALITY: {'CONFIRMED' if ok else 'NOT CONFIRMED'}")
    (HERE / "runs" / "retrieval_recall").mkdir(parents=True, exist_ok=True)
    (HERE / "runs" / "retrieval_recall" / "anchor_neutrality.json").write_text(
        json.dumps({"before": dict(raw_old), "after": dict(raw_new),
                    "mismatch_chunks": mismatch_chunks}, indent=2), encoding="utf-8")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
