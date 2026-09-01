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

    # --- attribution
    a_own = attribute_claim("We propose X. Our method achieved a Dice score of 0.91 on the test set.",
                            "Our method achieved a Dice score of 0.91")
    check("attribute: first-person result -> OWN_PAPER", a_own["attribution"] == OWN_PAPER, str(a_own))
    a_cite = attribute_claim("Smith et al. reported 0.87 Dice on a different cohort.",
                             "Smith et al. reported 0.87 Dice")
    check("attribute: 'Smith et al. reported' -> CITED_PAPER", a_cite["attribution"] == CITED_PAPER, str(a_cite))
    a_unk = attribute_claim("The Dice score was 0.9.", "The Dice score was 0.9")
    check("attribute: bare sentence -> UNKNOWN", a_unk["attribution"] == UNKNOWN, str(a_unk))

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
