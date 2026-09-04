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
    # Phase 5a — STRUCTURAL BINDING.
    # PDF-only paper: a quantitative OWN result can no longer be verified structurally
    # -> unverifiable_binding, NOT returned (this is the correction, not a regression).
    it = _gate_value("results", "The system achieved an nDCG@5 score of 0.4502.",
                     RCHUNKS, ["A Lin"])
    check("gate: PDF-only quantitative OWN result -> unverifiable_binding (not RETURNED)",
          it["final"] == ABSTAINED and it["abstain_reason"] == "unverifiable_binding", str(it))
    # Structured paper: value binds to the (own-row, metric-column) cell -> RETURNED
    SCELLS = [{"row_label": "Ours", "column_header": "nDCG@5", "value": "0.4502",
               "caption": "Results on the shared task.", "section": "results"},
              {"row_label": "Jones et al.", "column_header": "nDCG@5", "value": "0.61",
               "caption": "Results on the shared task.", "section": "results"}]
    SCH = [dict(RCHUNKS[0], representation="latex", block_type="table",
                table_cells=SCELLS, table_caption="Results on the shared task.")]
    it = _gate_value("results", "Our method reports an nDCG@5 of 0.4502.", SCH, ["A Lin"])
    check("gate: structured paper, value at own cell -> bound -> RETURNED",
          it["final"] == RETURNED and it["structural_binding"]["status"] == "bound", str(it))
    # Structured paper: cross-row number (0.61 is Jones' row) -> binding_wrong_cell
    it = _gate_value("results", "Our method reports an nDCG@5 of 0.61.", SCH, ["A Lin"])
    check("gate: structured paper, cross-row number -> binding_wrong_cell -> ABSTAINED",
          it["final"] == ABSTAINED and it["abstain_reason"] == "binding_wrong_cell", str(it))
    # 5b — structured paper, metric IS a column but the claimed value is a prose
    # aggregate in no cell of it -> not_a_table_claim -> falls through -> grounds -> RETURNED
    PCH = [dict(SCH[0], text="Averaged over five folds our system reaches a mean nDCG@5 of "
                             "0.4502 on the shared task, our own contribution.")]
    it = _gate_value("results", "Our system reaches a mean nDCG@5 of 0.44 across folds.", PCH, ["A Lin"])
    check("gate: structured paper, prose aggregate not in metric column -> not_a_table_claim (falls through)",
          it["structural_binding"]["status"] == "not_a_table_claim", str(it))
    # 5b — claim names a metric that is NO column anywhere -> not_bindable -> falls through
    it = _gate_value("results", "Our system reaches a BLEU of 34.1 on the shared task.", SCH, ["A Lin"])
    check("gate: structured paper, metric not a column anywhere -> not_bindable (falls through)",
          it["structural_binding"]["status"] == "not_bindable", str(it))

    # ------------------------------------------------------------------
    # SYMMETRIC METRIC MATCHING (F1) — permanent receipt that the claim side
    # and the column side of structural_bind use ONE rule (_metric_tokens).
    # Prior asymmetry: claim side dropped tokens < 4 chars (so "f1"/"auc" in a
    # claim were invisible -> genuinely tabulated columns came back not_bindable);
    # column side free-substring-matched (so "em" inside "Performance metrics"
    # made a non-metric column look bindable from one direction).
    # ------------------------------------------------------------------
    from src.evidence.gate import _metric_tokens, _col_matches_metric, structural_bind, _METRIC_TOKENS

    # (1) valid metric-column / claim pair that PREVIOUSLY failed now matches:
    #     "F1" is 2 chars -> _sig_tokens (len>=4) never yielded it -> old metric_toks
    #     was empty -> not_bindable even though the table has an F1 column.
    check("sym 1a: _metric_tokens sees short metric tokens ('f1', 'auc')",
          _metric_tokens("Our model reports an F1 of 0.88.") >= {"f1"}
          and _metric_tokens("AUC of 0.91") >= {"auc"})
    F1CELLS = [{"row_label": "Ours", "column_header": "F1", "value": "0.88",
                "caption": "Main results.", "section": "results"},
               {"row_label": "Prior et al.", "column_header": "F1", "value": "0.71",
                "caption": "Main results.", "section": "results"}]
    F1CH = [dict(RCHUNKS[0], representation="latex", block_type="table",
                 text="Main results. Ours F1 0.88 Prior et al. F1 0.71",
                 table_cells=F1CELLS, table_caption="Main results.")]
    sb = structural_bind("Our method reports an F1 of 0.88.", F1CH)
    check("sym 1b: claim 'F1 of 0.88' at own F1 cell -> bound (was not_bindable pre-fix)",
          sb["status"] == "bound", str(sb))
    sb = structural_bind("Our method reports an F1 of 0.71.", F1CH)
    check("sym 1c: claim 'F1 of 0.71' (Prior's row) -> wrong_cell (was not_bindable pre-fix)",
          sb["status"] == "wrong_cell", str(sb))

    # (2) a genuine non-match still does not match — no spurious substring hit.
    check("sym 2a: _metric_tokens('Performance metrics') is empty (no 'em' substring hit)",
          _metric_tokens("Performance metrics") == set(), str(_metric_tokens("Performance metrics")))
    check("sym 2b: _metric_tokens('Blood component used for measurement') is empty",
          _metric_tokens("Blood component used for measurement") == set())
    check("sym 2c: _col_matches_metric('Performance metrics', full vocab) is False (was True via 'em')",
          _col_matches_metric("Performance metrics", _METRIC_TOKENS) is False)
    check("sym 2d: _col_matches_metric('Blood component used for measurement', full vocab) is False",
          _col_matches_metric("Blood component used for measurement", _METRIC_TOKENS) is False)

    # (3) the SAME normalisation + token semantics on both sides.
    check("sym 3a: 'F1-score' and 'F1' share the token 'f1' under _metric_tokens (both sides)",
          _metric_tokens("F1-score (%)") & _metric_tokens("we report F1") == {"f1"})
    check("sym 3b: _col_matches_metric reduces its header arg with _metric_tokens too",
          _col_matches_metric("F1-score", {"f1"}) is True
          and _col_matches_metric("F1-score", {"em"}) is False)
    check("sym 3c: no side introduces 'em' from 'exact match' as a substring",
          _metric_tokens("Performance metrics").isdisjoint(_metric_tokens("exact match")))
    check("sym 3d: header vs claim symmetry — _col_matches_metric(h, toks(c)) == (toks(h) & toks(c))",
          all(_col_matches_metric(h, _metric_tokens(c)) ==
              bool(_metric_tokens(h) & _metric_tokens(c))
              for h, c in [("Accuracy (%)", "our accuracy is 0.9"),
                           ("Performance metrics", "a Performance metrics of 80.52"),
                           ("F1", "an F1 of 0.88"),
                           ("Dice coefficient", "a Dice of 0.9"),
                           ("True positive rate (%)", "a rate of 12")]))

    # (4) each of the 3 previously-accepted adversarial cases, re-evaluated post-fix.
    #     Compact biomedical table: a junk group header ("Performance metrics") plus
    #     the real metric columns. Outcome recorded for each.
    ADVCELLS = [{"row_label": r, "column_header": ch, "value": v, "caption": cap, "section": "results"}
                for cap in ["Comparative performance metrics analysis."]
                for r, ch, v in [("GA", "Accuracy (%)", "80.82"), ("CNN", "Accuracy (%)", "82.13"),
                                 ("K-SVM", "Accuracy (%)", "87.03"),
                                 ("GA", "Performance metrics", "80.52"),
                                 ("CNN", "Performance metrics", "83.21"),
                                 ("K-SVM", "Performance metrics", "87.82")]]
    ADVCH = [dict(RCHUNKS[0], representation="jats_xml", block_type="table",
                  text="Comparative performance metrics analysis. Methods Performance metrics "
                       "Accuracy (%) GA 80.52 80.82 CNN 83.21 82.13 K-SVM 87.82 87.03",
                  table_cells=ADVCELLS, table_caption="Comparative performance metrics analysis.")]
    # 4a/4b: the two originally-accepted claims named "Performance metrics" — a phrase
    #        with NO recognised metric word. Post-fix BOTH sides agree it names no
    #        metric -> not_bindable (a true residual, symmetric — not a confound).
    a1 = structural_bind("CNN reports a Performance metrics of 80.52 on the study cohort.", ADVCH)
    a2 = structural_bind("CNN reports a Performance metrics of 87.82 on the study cohort.", ADVCH)
    check("adv 4a: 'Performance metrics of 80.52' -> not_bindable (names no metric; symmetric residual)",
          a1["status"] == "not_bindable", str(a1))
    check("adv 4b: 'Performance metrics of 87.82' -> not_bindable (names no metric; symmetric residual)",
          a2["status"] == "not_bindable", str(a2))
    # 4c: the SAME cross-row attack expressed with the REAL metric name now BINDS and
    #     is caught — 80.82 is GA's Accuracy, attributed to CNN.
    a3 = structural_bind("CNN reports an Accuracy of 80.82 on the study cohort.", ADVCH)
    check("adv 4c: same cross-row attack via real metric 'Accuracy' -> wrong_cell (caught post-fix)",
          a3["status"] == "wrong_cell", str(a3))
    # 4d: cross-table substitution case named "Blood component used for measurement" — also
    #     no recognised metric word -> not_bindable, symmetric.
    a4 = structural_bind("Arsenic reports a Blood component used for measurement of 12 on the cohort.", ADVCH)
    check("adv 4d: 'Blood component used for measurement of 12' -> not_bindable (names no metric)",
          a4["status"] == "not_bindable", str(a4))

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
