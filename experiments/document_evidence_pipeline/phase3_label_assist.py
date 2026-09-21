"""Label-assistance harness for the locked Phase 3 90-item sample.

NOT a phase. Produces no rates, no denominator, no detector, no precision/recall.
It is a DISAGREEMENT DETECTOR: its job is to surface the hard cases to Prakash.
Routing most items to him is success, not failure.

ANTI-LEAKAGE (absolute): this module must never open suggested_labels.json or
labels.json. Only the raw sample records are read. Enforced by _assert_no_leak().

Judge: one model family is installed in this environment (qwen2.5:7b). There is no
second family, so per the brief we do NOT pretend to have one -- the same model is
run twice with two deliberately different framings, temperature 0, independent
calls, neither call seeing the other.
"""
from __future__ import annotations

import json
import random
import re
import sys
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
SAMPLE = HERE / "runs" / "phase3_composition"
OUT = HERE / "runs" / "phase3_label_assist"

SEED = 42
MODEL = "qwen2.5:7b"
PROMPT_VERSION = "label-assist-v1"
OLLAMA = "http://localhost:11434/api/generate"
FORBIDDEN = {"suggested_labels.json", "labels.json", "summary.json"}

# ---- verbatim questions -----------------------------------------------------
Q_A = ("Is this a real extracted fact? Y = a fact. N = not a fact (section number, "
       "number fragment, DOI/URL piece, citation marker, empty or sub-token text).")
Q_B = "Does this metric name actually belong to this value? Y / N."

F2_A = ("Could this text stand alone as a claim in a results table? If it is a fragment "
        "of a larger number, a locator, or a reference, it cannot.")
# The brief supplies a second framing for Task A only. This one is authored here for
# Task B and is reported verbatim; it is a restatement test rather than a membership test.
F2_B = ("If you wrote only \"<name> = <value>\" on a slide, would that be a correct "
        "statement of what this text reports? Y / N.")


def _assert_no_leak(path: Path) -> None:
    if path.name in FORBIDDEN:
        raise AssertionError(f"ANTI-LEAKAGE VIOLATION: refused to read {path.name}")


def load(name: str):
    p = SAMPLE / name
    _assert_no_leak(p)
    return json.loads(p.read_text(encoding="utf-8"))


# ---- deterministic triage: can only prove garbage, never validity ------------
_DOI_URL = re.compile(r"(?:https?://\S+|10\.\d{4,9}/\S+|arxiv\.org/\S+|doi\.org/\S+)", re.I)
_BRACKET_CITE = re.compile(r"\[([\d,\s–—-]+)\]")
_SUPER_CITE = re.compile(r"[a-z],(\d{1,3}(?:,\d{1,3})+)")
_HEADING = re.compile(r"^\s*(\d+(?:\.\d+)*)\.?\s+[A-Z]")


def triage(value: str, window: str) -> list[str]:
    """Return the names of every OBVIOUS_MALFORMED rule that fired. Empty == REVIEW.

    Deliberately asymmetric: there is no OBVIOUS_VALID bucket. A bare number is
    always REVIEW -- '815' from '4,815 patients' and '815 patients' are
    indistinguishable unless the window settles it, which R3 checks explicitly.
    """
    fired = []
    w = " ".join(window.split())

    # R1 -- the value lives inside a DOI or URL token
    if any(value in tok for tok in _DOI_URL.findall(w)):
        fired.append("R1_DOI_URL_SUBSTRING")

    # R2 -- the value is a bare citation marker
    cites = set()
    for grp in _BRACKET_CITE.findall(w) + _SUPER_CITE.findall(w):
        cites.update(x.strip() for x in re.split(r"[,\s–—-]+", grp) if x.strip())
    if value in cites:
        fired.append("R2_CITATION_MARKER")

    # R3 -- empty window, or EVERY occurrence of the value is a sub-token of a
    #       longer number (e.g. '815' only ever appearing inside '4,815').
    if not w.strip():
        fired.append("R3_EMPTY_OR_SUBTOKEN")
    else:
        occ = [m.start() for m in re.finditer(re.escape(value), w)]
        if occ:
            def subtoken(i: int) -> bool:
                before = w[:i]
                after = w[i + len(value):]
                return bool(re.search(r"[\d](?:,|\.)?$", before) or re.match(r"\d", after))
            if all(subtoken(i) for i in occ):
                fired.append("R3_EMPTY_OR_SUBTOKEN")

    # R4 -- the window opens with this number as a section heading
    m = _HEADING.match(w)
    if m and m.group(1) == value:
        fired.append("R4_BARE_SECTION_NUMBER")

    return fired


# ---- judge ------------------------------------------------------------------
def ask(prompt: str) -> dict:
    body = json.dumps({
        "model": MODEL, "prompt": prompt, "stream": False, "format": "json",
        "options": {"temperature": 0, "seed": SEED, "num_predict": 200},
    }).encode()
    req = urllib.request.Request(OLLAMA, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=180) as r:
        raw = json.loads(r.read().decode())["response"]
    try:
        d = json.loads(raw)
    except json.JSONDecodeError:
        return {"answer": "UNCERTAIN", "reason": f"unparseable judge output: {raw[:200]}"}
    a = str(d.get("answer", "")).strip().upper()
    if a not in ("Y", "N"):
        a = "UNCERTAIN"
    return {"answer": a, "reason": str(d.get("reason", ""))[:400]}


def build_prompt(question: str, evidence: str) -> str:
    return (f"{question}\n\n"
            f"{evidence}\n\n"
            'Answer strictly as JSON: {"answer": "Y" or "N" or "UNCERTAIN", '
            '"reason": "<one sentence>"}')


def evidence_a(r: dict) -> str:
    return f'VALUE: {r["value"]}\nTEXT: {" ".join(r["window"].split())[:600]}'


def evidence_b(r: dict) -> str:
    return (f'VALUE: {r["value"]}\nNAME: {r["metric_found"]}\n'
            f'TEXT: {" ".join(r["window"].split())[:600]}')


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    su, sn = load("sample_unnamed.json"), load("sample_named.json")
    assert [r["sample_id"] for r in su] == [f"U{i:02d}" for i in range(1, 61)]
    assert [r["sample_id"] for r in sn] == [f"N{i:02d}" for i in range(1, 31)]

    triage_rec, judg, routing = [], [], []

    items = ([("A", r, Q_A, F2_A, evidence_a) for r in su]
             + [("B", r, Q_B, F2_B, evidence_b) for r in sn])

    for task, r, q1, q2, ev in items:
        sid = r["sample_id"]
        # deterministic rules answer the malformed question only -> Task A only
        fired = triage(r["value"], r["window"]) if task == "A" else []
        status = "OBVIOUS_MALFORMED" if fired else ("REVIEW" if task == "A" else "NOT_APPLICABLE")
        triage_rec.append({"id": sid, "task": task, "deterministic_status": status,
                           "rules_fired": fired})

        e = ev(r)
        f1 = ask(build_prompt(q1, e))
        f2 = ask(build_prompt(q2, e))
        judg.append({"id": sid, "task": task,
                     "framing_1": {"question": q1, **f1},
                     "framing_2": {"question": q2, **f2}})

        if f1["answer"] == "UNCERTAIN" or f2["answer"] == "UNCERTAIN":
            route, why, prov = "HUMAN_AUDIT", "a framing returned UNCERTAIN", None
        elif f1["answer"] != f2["answer"]:
            route, why, prov = "HUMAN_AUDIT", "framings disagree", None
        elif f1["answer"] == "N" and fired:
            route, why, prov = "PROVISIONAL_N", f"both framings N and rules fired: {','.join(fired)}", "N"
        else:
            route, why, prov = "HUMAN_AUDIT", "framings agree but no deterministic rule fired", None

        routing.append({"id": sid, "task": task, "deterministic_status": status,
                        "rules_fired": fired,
                        "framing_1": f1["answer"], "framing_2": f2["answer"],
                        "route": route, "why": why,
                        "provisional_label": prov, "human_verified": False})
        print(f"{sid} {task} {status:18} f1={f1['answer']:9} f2={f2['answer']:9} -> {route}")

    # blind 20% re-audit of provisional-N, to catch over-firing rules
    prov_ids = [x["id"] for x in routing if x["route"] == "PROVISIONAL_N"]
    rng = random.Random(SEED)
    k = max(1, round(0.20 * len(prov_ids))) if prov_ids else 0
    audit_extra = sorted(rng.sample(prov_ids, k)) if k else []
    for x in routing:
        x["in_blind_audit_sample"] = x["id"] in audit_extra

    sheet_ids = sorted({x["id"] for x in routing if x["route"] == "HUMAN_AUDIT"} | set(audit_extra))
    rec = {r["sample_id"]: r for r in su + sn}
    qof = {r["sample_id"]: (Q_A if r["sample_id"].startswith("U") else Q_B) for r in su + sn}
    evof = {r["sample_id"]: (evidence_a(r) if r["sample_id"].startswith("U") else evidence_b(r))
            for r in su + sn}

    lines = ["# Human audit sheet — Phase 3 sample", "",
             "Answer each with Y or N. Nothing here is pre-labelled.", "", "---", ""]
    for sid in sheet_ids:
        lines += [f"### {sid}", "", "```", evof[sid], "```", "",
                  f"**{qof[sid]}**", "", "-> Y / N", "", "---", ""]
    (OUT / "human_audit.md").write_text("\n".join(lines), encoding="utf-8")

    meta = {"seed": SEED, "model": MODEL, "prompt_version": PROMPT_VERSION,
            "second_model_family_available": False,
            "questions": {"task_A": Q_A, "task_B": Q_B,
                          "framing_2_task_A": F2_A, "framing_2_task_B": F2_B}}
    (OUT / "triage.json").write_text(json.dumps({"meta": meta, "items": triage_rec}, indent=1), encoding="utf-8")
    (OUT / "judgments.json").write_text(json.dumps({"meta": meta, "items": judg}, indent=1), encoding="utf-8")
    (OUT / "routing.json").write_text(json.dumps({"meta": meta, "items": routing}, indent=1), encoding="utf-8")

    from collections import Counter
    print("\nTRIAGE:", dict(Counter(x["deterministic_status"] for x in triage_rec)))
    print("ROUTING:", dict(Counter(x["route"] for x in routing)))
    agree = sum(1 for x in routing if x["framing_1"] == x["framing_2"])
    print(f"framing agreement: {agree}/{len(routing)} = {agree/len(routing):.1%}")
    print(f"provisional-N: {len(prov_ids)}, blind re-audit sample: {len(audit_extra)} {audit_extra}")
    print(f"audit sheet: {len(sheet_ids)} items -> {OUT/'human_audit.md'}")


if __name__ == "__main__":
    main()
