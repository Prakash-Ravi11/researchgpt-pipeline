"""Regression tests for the Phase 2.1 evaluator fixes: T5 title N/A, T6 author affiliation markers,
T7 page-1 arXiv stamp.

    .venv\\Scripts\\python.exe -m pytest -p no:cacheprovider src/evaluation/bottleneck_diagnosis/test_phase2_1_pdf_identity.py -q

Synthetic inputs only: no corpus, network, GPU or LLM. One test builds a two-line PDF in memory with
PyMuPDF to pin down how real extraction reports a raised affiliation marker. The corpus cases quoted in
comments come from the Phase 2 diagnosis.
"""
import pymupdf

from phase2_1_pdf_identity import (decide_v2, pdf_lines, span_chars, t5_title_check, t6_author_check,
                                   t6_classify_surname, t7_arxiv_check)


def span(text, size=10.0, flags=0, y=100.0):
    """One span in PyMuPDF 'dict' shape (only the keys the evaluator reads)."""
    return {"text": text, "size": size, "flags": flags, "origin": (72.0, y)}


def line(*spans, page=1):
    return page, span_chars(list(spans))


SUPERSCRIPT = 1   # MuPDF span flag bit 0


# --- T5: title -----------------------------------------------------------------------------------
def test_t5_not_reported_title_is_na():
    r = t5_title_check("NOT_REPORTED", "Brain Tumor Identification and Classification of MRI images")
    assert (r["T5"], r["T5p"], r["outcome"]) == (None, None, "na_title_not_reported")


def test_t5_reported_titles_keep_the_phase2_rule():
    head = ("UM-CAM: Uncertainty-weighted\nMulti-resolution Class Activation Maps for\n"
            "Weakly-supervised Fetal Brain Segmentation\nJia Fu1, Tao Lu2")
    title = ("UM-CAM: Uncertainty-weighted Multi-resolution Class Activation Maps for "
             "Weakly-supervised Fetal Brain Segmentation")
    assert t5_title_check(title, head)["T5"] is True
    assert t5_title_check("A Completely Different Paper Title", head)["T5"] is False


# --- T6: authors -----------------------------------------------------------------------------------
def test_t6_unicode_superscript_marker_matches():
    r = t6_classify_surname("Smith", [line(span("Jane Smith¹, John Doe²"))])
    assert (r["class"], r["marker_evidence"]) == ("match_trailing_marker", "unicode_superscript")


def test_t6_digit_in_pdf_superscript_span_matches():
    # corpus shape P001: 'Valentin Comte' 10pt + '1' 7pt, MuPDF superscript flag set
    r = t6_classify_surname("Smith", [line(span("Jane Smith", 10, 4, 100), span("1", 7, 4 | SUPERSCRIPT, 96.4),
                                           span(", John Doe", 10, 4, 100))])
    assert (r["class"], r["marker_evidence"], r["pdf_raw"]) == ("match_trailing_marker", "mupdf_superscript_flag", "Smith[sup:1]")


def test_t6_digit_in_smaller_raised_span_matches():
    # corpus shape P015: 'Verdera' 11pt + '3,4' 6pt raised 2.8pt, no superscript flag
    r = t6_classify_surname("Smith", [line(span("Jane Smith", 11, 4, 173.9), span("3,4", 6, 4, 171.1))])
    assert (r["class"], r["marker_evidence"]) == ("match_trailing_marker", "smaller_raised_span")


def test_t6_plain_glued_digit_is_not_a_match():
    # no superscript flag, same size, same baseline: extraction does not establish an affiliation marker
    for ln in (line(span("Jane Smith1, John Doe")), line(span("Jane Smith"), span("1, John Doe"))):
        assert t6_classify_surname("Smith", [ln])["class"] == "ambiguous_unconfirmed_marker"


def test_t6_different_surname_is_a_mismatch():
    assert t6_classify_surname("Smith", [line(span("Jane Smyth, John Doe"))])["class"] == "mismatch_not_found"
    assert t6_classify_surname("Smith", [line(span("Jane Smithson, John Doe"))])["class"] == "mismatch_not_found"


def test_t6_substring_inside_another_word_never_matches():
    # corpus P004: candidate 'Lu' must not match inside 'Multi-resolution'
    assert t6_classify_surname("Lu", [line(span("Multi-resolution Class Activation Maps"))])["class"] == "mismatch_not_found"


def test_t6_normalization_stage_is_recorded():
    r = t6_classify_surname("Alenya", [line(span("Mireia Alenyà, Andrea Urru"))])
    assert (r["class"], r["rule"]) == ("match_normalized", "diacritics_folded")
    r = t6_classify_surname("Guffens", [line(span("Frédéric Guﬀens"))])             # U+FB00 ligature
    assert (r["class"], r["rule"]) == ("match_normalized", "compatibility_decomposed")
    r = t6_classify_surname("Erdoğmuş", [line(span("Deniz Erdo˘gmu¸s"))])      # LaTeX spacing accents
    assert (r["class"], r["rule"]) == ("match_normalized", "pdf_spacing_accents_and_punctuation")
    assert t6_classify_surname("Comte", [line(span("Valentin Comte, Mireia"))])["class"] == "match_exact"


def test_t6_normalization_never_rescues_a_different_name():
    # corpus P027: candidate 'Erdoğan', the PDF prints 'Erdo˘gmu¸s' (= Erdoğmuş)
    assert t6_classify_surname("Erdoğan", [line(span("Deniz Erdo˘gmu¸s"))])["class"] == "mismatch_not_found"


def test_t6_candidate_that_absorbed_a_marker_is_a_mismatch():
    # corpus P007: candidate 'Agarwala', the PDF prints 'Agarwal' + superscript affiliation 'a'
    r = t6_classify_surname("Agarwala", [line(span("Nivedita Agarwal", 10, 4, 100), span("a", 7, 4 | SUPERSCRIPT, 96.4),
                                              span(", Tommaso", 10, 4, 100))])
    assert (r["class"], r["pdf_raw"]) == ("mismatch_candidate_includes_marker", "Agarwal[sup:a]")


def test_t6_na_and_unchanged_threshold():
    assert t6_author_check("NOT_REPORTED", [])["T6"] is None
    lines = [line(span("Jane Smith"), span("1", 7, SUPERSCRIPT, 96.4), span(", John Doe"))]
    r = t6_author_check("Jane Smith; John Doe; Ann Lee", lines)
    assert (r["found"], r["total"], r["T6"]) == (2, 3, True)          # 2/3 >= 0.5, as in Phase 2


def test_t6_real_pdf_extraction_semantics():
    doc = pymupdf.open()
    page = doc.new_page()
    x = 72 + pymupdf.get_text_length("Jane Smith", fontname="helv", fontsize=10)
    page.insert_text((72, 100), "Jane Smith", fontname="helv", fontsize=10)
    page.insert_text((x, 96), "1", fontname="helv", fontsize=7)                  # raised, smaller
    page.insert_text((72, 140), "John Brown2, Ann Lee", fontname="helv", fontsize=10)   # plain, same size
    lines = pdf_lines(doc)
    assert t6_classify_surname("Smith", lines)["class"] in ("match_trailing_marker", "match_exact")
    assert t6_classify_surname("Brown", lines)["class"] == "ambiguous_unconfirmed_marker"
    assert t6_classify_surname("Lee", lines)["class"] == "match_exact"


# --- T7: arXiv ---------------------------------------------------------------------------------------
STAMP_P1 = "arXiv:2306.11490v1  [cs.CV]  20 Jun 2023\nUM-CAM: Uncertainty-weighted Multi-resolution"


def test_t7_page1_stamp_matches():
    r = t7_arxiv_check("2306.11490v1", [STAMP_P1, "body", "references"])
    assert (r["T7"], r["outcome"]) == (True, "pass_page1_stamp")


def test_t7_reference_only_is_not_the_papers_identity():
    # corpus P012: the candidate id is a cited paper's id on page 9
    pages = ["Brain Tumor Identification (no stamp)", "body",
             "[4] Samavi, S. (2018). arXiv preprint\narXiv:1809.07786.\n5. Pan, Y."]
    r = t7_arxiv_check("1809.07786", pages)
    assert (r["T7"], r["outcome"]) == (False, "fail_no_page1_stamp")
    assert [o["page"] for o in r["observed"] if o["id"] == "1809.07786"] == [3]      # rejected id kept for audit


def test_t7_unrelated_page1_arxiv_id_does_not_match():
    pages = ["arXiv:2101.00001v2  [eess.IV]  4 Jan 2021\nSome Title", "see arXiv:2306.11490"]
    r = t7_arxiv_check("2306.11490", pages)
    assert (r["T7"], r["outcome"]) == (False, "fail_page1_stamp_is_other_id")


def test_t7_page1_mention_that_is_not_a_stamp_is_not_identity():
    r = t7_arxiv_check("2306.11490", ["Title\nCode and preprint: arXiv:2306.11490, see also [3]."])
    assert r["T7"] is False and r["page1_stamps"] == []


def test_t7_version_must_agree_when_stated():
    assert t7_arxiv_check("2306.11490v2", [STAMP_P1])["outcome"] == "fail_version_differs"
    assert t7_arxiv_check("2306.11490", [STAMP_P1])["T7"] is True


def test_t7_not_reported_is_na():
    assert t7_arxiv_check("NOT_REPORTED", [STAMP_P1])["T7"] is None


# --- decision -------------------------------------------------------------------------------------
def test_na_title_is_neutral_in_the_decision():
    t = {"T1": True, "T2": True, "T3": True, "T4": True, "T5": None, "T5p": None, "T6": None,
         "T7": False, "T8": True, "T9": True, "T9_rate": 1.0}
    assert decide_v2(t) == ("MATCH_WITH_DISCREPANCY", "medium", ["T7"])
    assert decide_v2({**t, "T7": None}) == ("MATCH_VERIFIED", "high", [])
