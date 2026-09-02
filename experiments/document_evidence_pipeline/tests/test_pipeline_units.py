"""LEVEL 1 - deterministic unit/smoke tests. No network, no LLM.

Run:  python -m tests.test_pipeline_units      (from experiments/document_evidence_pipeline/)
"""
from __future__ import annotations

import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline import schema  # noqa: E402
from pipeline.acquire import identity_validate, content_validate  # noqa: E402
from pipeline.represent import build_document, blocks_from_jats  # noqa: E402
from pipeline.chunker import chunk_document  # noqa: E402
from pipeline.attribute import attribute_claim  # noqa: E402
from pipeline.decide import decide  # noqa: E402
from pipeline.schema import (REPR_PDF, REPR_JATS, OWN_PAPER, CITED_PAPER, UNKNOWN,  # noqa: E402
                             EXPLICIT, INFERRED, MISSING, UNSUPPORTED, RETURNED, ABSTAINED,
                             evidence_item)

_PASS = _FAIL = 0
_FAILURES: list[str] = []


def check(name: str, cond: bool, detail: str = ""):
    global _PASS, _FAIL
    if cond:
        _PASS += 1
        print(f"  ok   {name}")
    else:
        _FAIL += 1
        _FAILURES.append(f"{name} :: {detail}")
        print(f"  FAIL {name}  {detail}")


def tiny_pdf(title: str, body_paras: int = 40) -> bytes:
    import pymupdf
    doc = pymupdf.open()
    para = (" This is a substantive paragraph describing the proposed method and its "
            "experimental evaluation on a benchmark dataset with reported accuracy and Dice score.")
    full = title + ".\n\n" + "".join(f"Paragraph {i}." + para + "\n\n" for i in range(body_paras))
    # many pages so the synthetic PDF clears the real >=20KB pre-filter, like a real paper
    npages = 1 if body_paras <= 2 else 30
    per = max(1, len(full) // 4) if npages > 1 else len(full)
    for pi in range(npages):
        p = doc.new_page()
        p.insert_textbox(pymupdf.Rect(56, 56, 556, 736), full[pi * per:(pi + 1) * per] or full[:400],
                         fontsize=8)
    out = doc.tobytes()
    doc.close()
    return out


JATS = b"""<?xml version="1.0"?>
<article xmlns:xlink="http://www.w3.org/1999/xlink">
<front><article-meta><title-group><article-title>Deep Carotid Segmentation Network</article-title></title-group>
<contrib-group><contrib><name><surname>Rossi</surname><given-names>A</given-names></name></contrib></contrib-group>
<abstract><p>We present a segmentation approach evaluated on a clinical ultrasound dataset.</p></abstract>
</article-meta></front>
<body>
<sec><title>Methods</title><p>%s</p><sec><title>Bilateral filter</title><p>%s</p></sec></sec>
<sec><title>Results</title><p>Our method achieved a Dice score of 0.91 on the held-out set.</p>
<p>Smith et al. reported 0.87 Dice on a different cohort.</p></sec>
</body></article>""" % (b"Detailed methodology paragraph. " * 80, b"Filter detail paragraph. " * 80)


def run():
    # --- schema
    rec = schema.canonical_acquisition_record("p1")
    rec.update(status=schema.FULL_TEXT, representation_type=REPR_PDF)
    rec["identity_validation"]["passed"] = True
    rec["content_validation"]["passed"] = True
    check("schema.valid FULL_TEXT record", schema.validate_acquisition_record(rec) == [])
    rec["content_validation"]["passed"] = False
    check("schema.rejects FULL_TEXT w/o content validation",
          schema.validate_acquisition_record(rec) != [])

    # --- content validation
    real_pdfs = sorted((ROOT / "pipeline" / "cache").glob("*.pdf"))
    if real_pdfs:
        check("content_validate accepts a real downloaded pdf",
              content_validate(REPR_PDF, real_pdfs[0].read_bytes())["passed"],
              real_pdfs[0].name)
    else:
        check("content_validate accepts a big synthetic pdf (no cached pdf present)",
              content_validate(REPR_PDF, tiny_pdf("A Real Paper Title", body_paras=400))["passed"])
    check("content_validate rejects html landing page",
          not content_validate(REPR_PDF, b"<!DOCTYPE html><html><body>Sign in to view</body></html>")["passed"])
    check("content_validate rejects empty",
          not content_validate(REPR_PDF, b"")["passed"])
    check("content_validate rejects tiny abstract-sized pdf",
          not content_validate(REPR_PDF, tiny_pdf("Stub", body_paras=1))["passed"])
    check("content_validate accepts JATS with sections+body",
          content_validate(REPR_JATS, JATS)["passed"])
    check("content_validate rejects JATS-shaped but thin",
          not content_validate(REPR_JATS, b"<article><body><sec><p>hi</p></sec></body></article>")["passed"])

    # --- identity validation (no wrong-paper acceptance)
    paper_right = {"title": "Deep Carotid Segmentation Network",
                   "authors": [{"name": "A Rossi"}], "externalIds": {}}
    paper_wrong = {"title": "A Completely Unrelated Study of Quantum Widgets",
                   "authors": [{"name": "Z Nobody"}], "externalIds": {}}
    check("identity_validate accepts matching JATS",
          identity_validate(paper_right, REPR_JATS, JATS)["passed"])
    check("identity_validate REJECTS wrong paper (JATS)",
          not identity_validate(paper_wrong, REPR_JATS, JATS)["passed"])
    pdf_bytes = tiny_pdf("Deep Carotid Segmentation Network")
    check("identity_validate accepts matching PDF",
          identity_validate(paper_right, REPR_PDF, pdf_bytes)["passed"])
    check("identity_validate REJECTS wrong paper (PDF)",
          not identity_validate(paper_wrong, REPR_PDF, pdf_bytes)["passed"])

    # --- representation + provenance
    acq = schema.canonical_acquisition_record("pX")
    acq.update(status=schema.FULL_TEXT, representation_type=REPR_JATS, source="europepmc")
    doc = build_document(acq, JATS)
    check("represent: JATS yields blocks", doc["n_blocks"] >= 4, str(doc["n_blocks"]))
    check("represent: results section detected", "results" in doc["sections_present"],
          str(doc["sections_present"]))
    check("represent: nested method subsection keeps 'method' label",
          any(b["section"] == "method" for b in doc["blocks"]))
    check("represent: every block has provenance",
          all(b["page_or_node"] and b["section"] and b["block_id"] for b in doc["blocks"]))
    chunks = chunk_document(doc)
    check("chunker: chunks carry section+loc+offsets",
          all(c["section"] and c["page_or_node"] and c["char_end"] > c["char_start"] for c in chunks))
    check("chunker: no chunk crosses blocks",
          all(c["chunk_id"].split("#")[0] == c["block_id"] for c in chunks))

    # --- attribution (hierarchical) : Task-7 targeted set A-J + precision guards
    FIRST_PERSON_SECTION = (
        "We propose a hybrid retrieval pipeline. In this work we introduce a "
        "session-based reranking stage and we evaluate our method on three "
        "benchmarks. Our approach combines dense and sparse retrieval. "
        "We report all metrics on the held-out split.")

    # A. clearly OWN
    a = attribute_claim("We propose SPAR. SPAR achieves a 9.2% absolute improvement in retrieval accuracy.",
                        "SPAR achieves a 9.2% absolute improvement", section="results",
                        section_context=FIRST_PERSON_SECTION)
    check("attr A: 'we propose SPAR ... achieves' -> OWN", a["attribution"] == OWN_PAPER, str(a))
    # B. clearly CITED
    a = attribute_claim("Smith et al. achieved 94.2% F1 on Dataset X.", "94.2% F1",
                        section="introduction_related_work")
    check("attr B: 'Smith et al. achieved 94.2%' -> CITED", a["attribution"] == CITED_PAPER, str(a))
    # C. passive voice in a first-person results section -> OWN via section-subject
    a = attribute_claim(
        "Retrieval was generally effective, as indicated by high context precision and recall scores.",
        "high context precision and recall scores", section="results",
        section_context=FIRST_PERSON_SECTION)
    check("attr C: passive voice in first-person results section -> OWN", a["attribution"] == OWN_PAPER, str(a))
    # C2. same passive sentence but NO first-person section context -> stays UNKNOWN (no guessing)
    a = attribute_claim(
        "Retrieval was generally effective, as indicated by high context precision and recall scores.",
        "high context precision and recall scores", section="results",
        section_context="This section reports numbers. Effectiveness was measured across systems.")
    check("attr C2: passive voice, no first-person cues -> UNKNOWN", a["attribution"] == UNKNOWN, str(a))
    # D. "our method achieved"
    a = attribute_claim("Our method achieved a Dice score of 0.91 on the test set.",
                        "Dice score of 0.91", section="results")
    check("attr D: 'our method achieved' -> OWN", a["attribution"] == OWN_PAPER, str(a))
    # E. table result with an 'ours' caption
    TBL = ("Table 5 Ablation study performance metrics. The (-) symbol denotes the reference "
           "proposed system. Configuration Dice Accuracy. Ablation 1 (No Preprocess) 84.82 99.18. "
           "Proposed 90.76 99.54.")
    a = attribute_claim(TBL, "Proposed 90.76 99.54", block_type="table", section="results")
    check("attr E: table 'Proposed' row with proposed-system caption -> OWN", a["attribution"] == OWN_PAPER, str(a))
    # F. ablation-table variant row must NOT be CITED (the old 'vs.' bug)
    a = attribute_claim(TBL, "Ablation 1 (No Preprocess) 84.82 99.18", block_type="table", section="results")
    check("attr F: ablation variant row -> not CITED", a["attribution"] != CITED_PAPER, str(a))
    # G. metric stated in Methods, first-person
    a = attribute_claim("For each approach, we evaluate performance using Exact Match and F1.",
                        "Exact Match and F1", section="method")
    check("attr G: 'we evaluate using ...' in Methods -> OWN", a["attribution"] == OWN_PAPER, str(a))
    # H. metric in Results, first-person
    a = attribute_claim("In Table 3 we report K-Precision and Recall for each variant.",
                        "K-Precision and Recall", section="results")
    check("attr H: 'we report ...' in Results -> OWN", a["attribution"] == OWN_PAPER, str(a))
    # I/J. abstract-only / inaccessible: bare sentence, no section context -> UNKNOWN
    a = attribute_claim("The Dice score was 0.9.", "Dice score was 0.9")
    check("attr I/J: bare sentence, no context -> UNKNOWN", a["attribution"] == UNKNOWN, str(a))
    # precision guard: citation marker hugging the number -> CITED even with 'we' in sentence
    a = attribute_claim("Unlike prior work by Smith et al. [12] which reached 92%, we target robustness.",
                        "92%", section="introduction_related_work")
    check("attr guard: number hugging '[12]' -> CITED", a["attribution"] == CITED_PAPER, str(a))
    # self-citation discount: own author surname in an 'et al.' -> not penalised
    a = attribute_claim("Building on our earlier study (Chen et al., 2022), we achieve 88% accuracy.",
                        "we achieve 88% accuracy", section="results",
                        own_author_surnames=["Wei Chen", "A. Kumar"])
    check("attr self-cite: own-author 'Chen et al.' discounted -> OWN", a["attribution"] == OWN_PAPER, str(a))

    # --- abstention gate
    it = evidence_item("results"); it.update(evidence_status=MISSING)
    check("decide: MISSING -> ABSTAINED", decide(it)["final"] == ABSTAINED)
    it = evidence_item("results"); it.update(evidence_status=UNSUPPORTED, provenance_valid=False)
    check("decide: UNSUPPORTED -> ABSTAINED", decide(it)["final"] == ABSTAINED)
    it = evidence_item("results"); it.update(evidence_status=EXPLICIT, provenance_valid=True,
                                             attribution=CITED_PAPER)
    check("decide: EXPLICIT but CITED result -> ABSTAINED", decide(it)["final"] == ABSTAINED)
    it = evidence_item("results"); it.update(evidence_status=EXPLICIT, provenance_valid=True,
                                             attribution=UNKNOWN)
    check("decide: EXPLICIT result, ownership UNKNOWN -> ABSTAINED", decide(it)["final"] == ABSTAINED)
    it = evidence_item("results"); it.update(evidence_status=EXPLICIT, provenance_valid=True,
                                             attribution=OWN_PAPER)
    check("decide: EXPLICIT OWN result -> RETURNED", decide(it)["final"] == RETURNED)
    it = evidence_item("dataset"); it.update(evidence_status=INFERRED, provenance_valid=True)
    check("decide: INFERRED dataset -> ABSTAINED (quantitative field)", decide(it)["final"] == ABSTAINED)
    it = evidence_item("method"); it.update(evidence_status=INFERRED, provenance_valid=True,
                                            attribution=UNKNOWN)
    check("decide: INFERRED method -> RETURNED (non-quantitative)", decide(it)["final"] == RETURNED)

    # --- evidence gate: number-anchored results grounding (RESULTS_GATE_TUNING_REPORT)
    from src.evidence.gate import _ground, _gate_value
    RCHUNKS = [
        {"text": "We propose SPAR and evaluate our system. The system achieved an nDCG@5 score "
                 "of 0.4502, competitive with the organizer baseline.", "section": "results",
                 "page_or_node": "p6", "block_id": "P:5", "block_type": "paragraph",
                 "representation": "pdf", "source": "arxiv", "char_start": 0, "char_end": 150},
        {"text": "Related work. Prior systems by Jones et al. reported an nDCG of 0.61 on a "
                 "different collection.", "section": "introduction_related_work",
                 "page_or_node": "p2", "block_id": "P:1", "block_type": "paragraph",
                 "representation": "pdf", "source": "arxiv", "char_start": 0, "char_end": 90},
    ]
    # LLM paraphrase of the paper's own result; number is verbatim in a body chunk
    g = _ground("The system achieved an nDCG@5 score of 0.4502 on the shared task.",
                RCHUNKS, field="results")
    check("gate: paraphrased result, number verbatim in body -> grounds",
          g is not None and g[0]["section"] == "results" and "0.4502" in g[1], str(g))
    # number NOT present anywhere -> not grounded -> gate abstains
    g2 = _ground("Our approach reached 88.3% accuracy on the test set.", RCHUNKS, field="results")
    check("gate: result number absent from every chunk -> not grounded", g2 is None, str(g2))
    # single-digit identifier ("BLEU-4") must not anchor a result
    idc = [{"text": "The evaluation used BLEU-4 and ROUGE-L as automatic metrics.",
            "section": "experimental_setup", "page_or_node": "p4", "block_id": "P:3",
            "block_type": "paragraph", "representation": "pdf", "source": "arxiv",
            "char_start": 0, "char_end": 70}]
    g3 = _ground("Improvements were observed on BLEU-4 across all baselines.", idc, field="results")
    check("gate: 'BLEU-4' single digit does not number-anchor a result", g3 is None, str(g3))
    # metrics grounding unchanged: short near-verbatim value still matches by token containment
    it = _gate_value("metrics", "nDCG@5", RCHUNKS, ["A Lin"])
    check("gate: metrics value still grounds via token containment",
          it["evidence_status"] == EXPLICIT and it["provenance_valid"], str(it))
    # full gate: paraphrased OWN result with grounded number -> RETURNED
    it = _gate_value("results", "The system achieved an nDCG@5 score of 0.4502.",
                     RCHUNKS, ["A Lin"])
    check("gate: grounded OWN paraphrased result -> RETURNED",
          it["final"] == RETURNED and it["attribution"] == OWN_PAPER, str(it))

    print(f"\n{_PASS} passed, {_FAIL} failed")
    if _FAILURES:
        print("FAILURES:")
        for f in _FAILURES:
            print("  -", f)
    return _FAIL == 0


if __name__ == "__main__":
    try:
        ok = run()
    except Exception:
        traceback.print_exc()
        ok = False
    sys.exit(0 if ok else 1)
