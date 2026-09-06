"""Deterministic reproducibility probes -- no LLM, no GPU, no network.

Re-derives every EXACT item in expected_results.json from the frozen run artifacts
shipped in reproducibility/artifacts/ and from source, and reports PASS / FAIL /
SKIPPED per item. APPROXIMATE items are listed but not asserted; they need a full
re-run and a judge model.

  python reproducibility/verify_deterministic.py

EXPECTED_CHECKS is 36. A check whose input file is absent is reported SKIPPED by
name -- never silently omitted -- and any SKIPPED at all makes the run non-zero.

Exit 0 IFF passed == 36 and failed == 0 and skipped == 0.
"""
from __future__ import annotations
import json, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPRO = Path(__file__).resolve().parent
# The six result-bearing inputs are SHIPPED here, not read from the gitignored
# runs/ tree. Reading only this directory is deliberate: if a shipped copy is
# missing, the affected checks must SKIP, not silently fall back to a local run
# directory that a reproducer does not have.
ARTIFACTS = REPRO / "artifacts"
EXPECTED_CHECKS = 36
P = F = S = 0
results = []


def check(name, got, want, tol=0):
    global P, F
    if isinstance(want, (int, float)) and isinstance(got, (int, float)):
        ok = abs(got - want) <= tol
    else:
        ok = got == want
    results.append({"check": name, "expected": want, "got": got, "tolerance": tol,
                    "status": "PASS" if ok else "FAIL"})
    if ok:
        P += 1
    else:
        F += 1
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}: got {got!r} want {want!r}"
          + (f" (+-{tol})" if tol else ""))
    return ok


def skip(names, reason):
    """Record checks that could not run. Never silent: each is named."""
    global S
    for name in names:
        S += 1
        results.append({"check": name, "expected": None, "got": None,
                        "status": "SKIPPED", "reason": reason})
        print(f"  [SKIP] {name}: {reason}")


def load(p):
    """Load a shipped artifact, or None if it is absent."""
    fp = ARTIFACTS / p
    return json.loads(fp.read_text(encoding="utf-8")) if fp.exists() else None


# check names per input file, so a missing input skips by name instead of vanishing
NAMES = {
    "parity_gate_precision/per_fallback.json": [
        "fallbacks measured", "justified", "over-triggered", "prose fired",
        "table fired", "caption fired", "deficit < 2%", "deficit >= 20%",
        "latex table survival >= pdf", "f3b06a914702 table survival 1.000/1.000",
        "f3b06a914702 discarded anyway"],
    "binding_validation/task3_probes.json": [
        "medical probes", "adversarial acceptances (any route)", "caught via wrong_cell"],
    "structural_binding/binding_probes.json": [
        "canonical probes", "canonical adversarial acceptances"],
    "gate_sensitivity/crossrow.json": [
        "crossrow probes", "crossrow acceptances"],
    "binding_validation/task1_verify.json": [
        "medical JATS structured cells", "medical JATS papers", "tables parsed to cells"],
    "eval_framework_sensitivity/per_mutant.json": [
        "evaluation-framework cases", "unscored cases"],
    "_invariant16": ["invariant-16 suite total"],
    "_manifests": [
        "canonical60 papers", "data_test8 papers", "medical50_frozen full-text",
        "medical50_reacquired full-text",
        "canonical60: every full-text file hashed", "data_test8: every full-text file hashed",
        "medical50_frozen: every full-text file hashed",
        "medical50_reacquired: every full-text file hashed"],
}
ABSENT = "input absent -- shipped artifact reproducibility/artifacts/{} not found"


def main() -> int:
    print("=" * 78); print("DETERMINISTIC REPRODUCIBILITY PROBES"); print("=" * 78)

    print("\n-- anchor rule (source of truth) --")
    anch = (ROOT / "src/evidence/anchors.py").read_text(encoding="utf-8")
    m = re.search(r'NUMERIC_ANCHOR_RE\s*=\s*re\.compile\(\s*r?["\']([^"\']+)', anch)
    check("anchor regex unchanged", m.group(1) if m else None, r"\d+\.\d+|\b\d{2,}\b")

    print("\n-- frozen config constants --")
    summ = (ROOT / "src/summarization/summarize.py").read_text(encoding="utf-8")
    r = re.search(r'EXTRACTION_OUTPUT_RESERVATION\s*=\s*(\d+)', summ)
    check("EXTRACTION_OUTPUT_RESERVATION", int(r.group(1)) if r else None, 768)
    par = (ROOT / "src/evidence/latex_parity.py").read_text(encoding="utf-8")
    r = re.search(r'DEFAULT_PARITY_TOLERANCE\s*=\s*([\d.]+)', par)
    check("DEFAULT_PARITY_TOLERANCE", float(r.group(1)) if r else None, 0.0)
    stag = (ROOT / "configs/staging_config.yaml").read_text(encoding="utf-8")
    check("latex_ingestion_enabled stays false",
          bool(re.search(r"latex_ingestion_enabled:\s*false", stag)), True)

    print("\n-- Table 4: parity gate (Criterion J) --")
    key = "parity_gate_precision/per_fallback.json"
    pg = load(key)
    if pg:
        check("fallbacks measured", len(pg), 12)
        check("justified", sum(1 for x in pg if x["verdict"] == "JUSTIFIED"), 12)
        check("over-triggered", sum(1 for x in pg if x["verdict"] == "OVER_TRIGGERED"), 0)
        check("prose fired", sum(1 for x in pg if "prose" in x["splits_fired"]), 12)
        check("table fired", sum(1 for x in pg if "table" in x["splits_fired"]), 4)
        check("caption fired", sum(1 for x in pg if "caption" in x["splits_fired"]), 1)
        check("deficit < 2%", sum(1 for x in pg if x["all_deficit"] < 0.02), 4)
        check("deficit >= 20%", sum(1 for x in pg if x["all_deficit"] >= 0.20), 4)
        check("latex table survival >= pdf",
              sum(1 for x in pg if x["table_n"] and x["table_latex"] >= x["table_pdf"]), 8)
        f3 = next((x for x in pg if x["paper_id"].startswith("f3b06a914702")), None)
        if f3:
            check("f3b06a914702 table survival 1.000/1.000",
                  (f3["table_latex"], f3["table_pdf"]), (1.0, 1.0))
            check("f3b06a914702 discarded anyway", f3["verdict"], "JUSTIFIED")
        else:
            skip(NAMES[key][-2:], "paper f3b06a914702 not present in per_fallback.json")
    else:
        skip(NAMES[key], ABSENT.format(key))

    print("\n-- Table 2: adversarial probes, post-F1 --")
    key = "binding_validation/task3_probes.json"
    t3 = load(key)
    if t3:
        adv = [x for x in t3 if x.get("class") != "correct_cell"]
        check("medical probes", len(t3), 13)
        check("adversarial acceptances (any route)",
              sum(1 for x in adv if x.get("final") == "RETURNED"), 0)
        check("caught via wrong_cell",
              sum(1 for x in t3 if x.get("binding_status") == "wrong_cell"), 12)
    else:
        skip(NAMES[key], ABSENT.format(key))

    key = "structural_binding/binding_probes.json"
    bp = load(key)
    if bp:
        check("canonical probes", len(bp), 16)
        check("canonical adversarial acceptances",
              sum(1 for x in bp if x.get("class") != "correct_cell" and x.get("final") == "RETURNED"), 0)
    else:
        skip(NAMES[key], ABSENT.format(key))

    key = "gate_sensitivity/crossrow.json"
    cr = load(key)
    if cr:
        check("crossrow probes", len(cr), 8)
        check("crossrow acceptances", sum(1 for x in cr if x.get("FOOLED")), 0)
    else:
        skip(NAMES[key], ABSENT.format(key))

    if t3 and bp and cr:
        check("invariant-16 suite total", len(t3) + len(bp) + len(cr), 37)
    else:
        skip(NAMES["_invariant16"], "needs all three probe files; at least one is absent")

    print("\n-- Table 5a: structural cells --")
    key = "binding_validation/task1_verify.json"
    tv = load(key)
    if tv:
        check("medical JATS structured cells", tv.get("total_cells"), 1371)
        check("medical JATS papers", len(tv.get("jats_ids", [])), 11)
        check("tables parsed to cells", tv.get("tables_structured"), 22)
    else:
        skip(NAMES[key], ABSENT.format(key))

    print("\n-- Table 3: case count (scores themselves are APPROXIMATE) --")
    key = "eval_framework_sensitivity/per_mutant.json"
    pm = load(key)
    if pm:
        check("evaluation-framework cases", len(pm), 106)
        check("unscored cases", sum(1 for x in pm if x.get("ragas_faithfulness") is None), 0)
    else:
        skip(NAMES[key], ABSENT.format(key))

    print("\n-- corpus manifests --")
    idx = REPRO / "manifests/index.json"
    if idx.exists():
        i = json.loads(idx.read_text(encoding="utf-8"))
        check("canonical60 papers", i.get("canonical60", {}).get("n_papers"), 60)
        check("data_test8 papers", i.get("data_test8", {}).get("n_papers"), 8)
        check("medical50_frozen full-text", i.get("medical50_frozen", {}).get("n_full_text"), 19)
        check("medical50_reacquired full-text", i.get("medical50_reacquired", {}).get("n_full_text"), 23)
        for c in ("canonical60", "data_test8", "medical50_frozen", "medical50_reacquired"):
            check(f"{c}: every full-text file hashed",
                  i.get(c, {}).get("n_full_text_without_local_file"), 0)
    else:
        skip(NAMES["_manifests"], "input absent -- reproducibility/manifests/index.json not found")

    accounted = P + F + S
    print("\n" + "=" * 78)
    print(f"{P} passed, {F} failed, {S} skipped, of {EXPECTED_CHECKS} expected")
    if accounted != EXPECTED_CHECKS:
        print(f"  ACCOUNTING ERROR: {accounted} checks accounted for, expected {EXPECTED_CHECKS}")
    if S:
        print("  SKIPPED checks are NOT passes. Restore the missing inputs and re-run;")
        print("  reproducibility/artifacts/PROVENANCE.json lists what belongs there.")
    ok = (P == EXPECTED_CHECKS and F == 0 and S == 0 and accounted == EXPECTED_CHECKS)
    print(f"  VERDICT: {'OK -- all 36 EXACT checks reproduced' if ok else 'INCOMPLETE -- see above'}")
    print("APPROXIMATE items are NOT asserted here - see expected_results.json; they need a")
    print("full re-run with the pinned judge model and carry explicit tolerances.")
    (REPRO / "verify_results.json").write_text(
        json.dumps({"passed": P, "failed": F, "skipped": S,
                    "expected_checks": EXPECTED_CHECKS, "ok": ok,
                    "checks": results}, indent=2), encoding="utf-8")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
