"""Run the 15 staging safety invariants against the medical binding-validation
outputs (runs/binding_validation/). Uses staging_run._check_invariants unchanged.

  python -u experiments/document_evidence_pipeline/binding_validation_invariants.py
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from src.evidence.gate import gate_paper, FULL_TEXT, EXPLICIT, RETURNED       # noqa: E402
from staging_run import _check_invariants                                     # noqa: E402
from staging_run import _adversarial_probe_acceptances as _adv_acc           # noqa: E402

REACQ = HERE / "runs" / "medical_reacquire"
PROC = HERE / "runs" / "binding_validation" / "processed"
META = REACQ / "raw_metadata" / "collected_papers.json"


def main() -> int:
    corpus = json.loads(META.read_text(encoding="utf-8"))
    chunks = json.loads((PROC / "chunks.json").read_text(encoding="utf-8"))
    ext_cache = json.loads((PROC / "extraction_cache.json").read_text(encoding="utf-8"))
    by_paper: dict[str, list[dict]] = defaultdict(list)
    for c in chunks:
        by_paper[c["paper_id"]].append(c)

    evidence = []
    g_checked = g_valid = 0
    noft_fields = noft_abstained = 0
    for p in corpus:
        pid = p["paperId"]
        acq = FULL_TEXT if p.get("has_full_text") else "NO_ACCESSIBLE_FULL_TEXT"
        e = ext_cache.get(pid, {})
        rec = {"paper_id": pid, "datasets": e.get("datasets"),
               "metrics": e.get("metrics"), "results": e.get("results")}
        sn = [a.get("name", "") for a in (p.get("authors") or []) if isinstance(a, dict)]
        gated = gate_paper(rec, by_paper.get(pid, []), acq, sn)
        evidence.append({"paper_id": pid, "acquisition_status": acq, "evidence": gated["evidence"]})
        for f, items in gated["evidence"].items():
            for it in items:
                if it.get("evidence_status") == EXPLICIT:
                    g_checked += 1
                    g_valid += 1 if it.get("provenance_valid") else 0
                if acq != FULL_TEXT:
                    noft_fields += 1
                    noft_abstained += 1 if it["final"] != RETURNED else 0

    gate_summary = {
        "provenance_checked": g_checked, "provenance_valid": g_valid,
        "provenance_valid_rate": (round(g_valid / g_checked, 4) if g_checked else None),
        "no_full_text_quant_fields": noft_fields,
        "no_full_text_quant_abstained": noft_abstained,
    }

    # Invariant 16 — the COMPLETE adversarial probe suite, BOTH domains, checked
    # route-agnostically (final outcome only). Medical JATS (Task 3), canonical
    # LaTeX (structural_binding_measure), and the gate_sensitivity cross-row probe.
    probe_files = [
        (HERE / "runs" / "binding_validation" / "task3_probes.json", "medical_jats"),
        (HERE / "runs" / "structural_binding" / "binding_probes.json", "canonical_latex"),
        (HERE / "runs" / "gate_sensitivity" / "crossrow.json", "crossrow"),
    ]
    adversarial_probes: list[dict] = []
    loaded = []
    for path, dom in probe_files:
        if path.exists():
            recs = json.loads(path.read_text(encoding="utf-8"))
            for r in recs:
                r.setdefault("domain", dom)
            adversarial_probes.extend(recs)
            loaded.append(f"{dom}:{len(recs)}")
        else:
            loaded.append(f"{dom}:MISSING")

    inv = _check_invariants(corpus, evidence, gate_summary, {}, by_paper, [],
                            adversarial_probes=adversarial_probes)
    accepted = _adv_acc(adversarial_probes)
    n_pass = sum(1 for v in inv.values() if v == "PASS")
    print(f"\n=== 16 SAFETY INVARIANTS — medical binding_validation ===")
    for k, v in inv.items():
        print(f"  {v:4}  {k}")
    print(f"\n  adversarial probe suite: {'  '.join(loaded)}  "
          f"(total {len(adversarial_probes)} probes)")
    print(f"  route-agnostic adversarial acceptances: {len(accepted)}")
    for a in accepted:
        print(f"    ACCEPTED [{a.get('domain')}/{a.get('paper_id')}] {a.get('class')}: {a.get('claim')}")
    print(f"\n  {n_pass}/{len(inv)} PASS")
    (HERE / "runs" / "binding_validation" / "invariants.json").write_text(
        json.dumps({"invariants": inv, "gate_summary": gate_summary,
                    "adversarial_probe_files": loaded,
                    "adversarial_acceptances": accepted}, indent=2), encoding="utf-8")
    return 0 if n_pass == len(inv) else 1


if __name__ == "__main__":
    raise SystemExit(main())
