"""Unit tests for the explicit rule-based claim extractor.

Deterministic, no corpus, no LLM. The contract test at the bottom is the one that
guards STOP CONDITION 4: what the extractor hands gate_paper must be re-split by
gate_paper into exactly the same sentences.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
EXP = HERE.parent
ROOT = EXP.parents[1]
for p in (str(ROOT), str(EXP)):
    if p not in sys.path:
        sys.path.insert(0, p)

import explicit_claims as EC  # noqa: E402
from src.evidence.gate import _SENT  # noqa: E402


def block(text, *, section="results", block_type="paragraph", char_start=0,
          block_id="P:1", page="p3"):
    return {"text": text, "section": section, "block_type": block_type,
            "char_start": char_start, "char_end": char_start + len(text),
            "block_id": block_id, "page_or_node": page}


def run(text, **kw):
    return EC.extract("PID", [block(text, **kw)])


def only_reason(text, **kw):
    """The single reason code every rejected sentence in `text` shares.

    _SENT may split one input into several sentences (a reference string with
    "Doe, J." does), so this asserts one DISTINCT code, not one row.
    """
    out = run(text, **kw)
    assert not out["claims"], f"expected rejection, got claim: {out['claims']}"
    assert out["rejections"], "expected at least one rejection"
    codes = {r["reason_code"] for r in out["rejections"]}
    assert len(codes) == 1, codes
    return codes.pop()


def one_claim(text, **kw):
    out = run(text, **kw)
    assert len(out["claims"]) == 1, (out["claims"], out["rejections"])
    return out["claims"][0]


# ---- the 7 NORM strings must all survive as claims -------------------------

NORM_SENTENCES = [
    ("NORM-1", "Our model achieves −0.4 correlation on the benchmark."),
    ("NORM-2", "Our model achieves 92.3 ± 0.4 accuracy on the benchmark."),
    ("NORM-3", "Our model achieves 92.3† accuracy on the benchmark."),
    ("NORM-4", "Our model achieves 92.3* accuracy on the benchmark."),
    ("NORM-5", "Our model achieves **92.3** accuracy on the benchmark."),
    ("NORM-6", "Our model achieves 92.3 % accuracy on the benchmark."),
    ("NORM-7", "Our model achieves an MAE of 1.2e-4 on the benchmark."),
]


@pytest.mark.parametrize("case,text", NORM_SENTENCES, ids=[c for c, _ in NORM_SENTENCES])
def test_norm_sentences_are_claims(case, text):
    c = one_claim(text)
    assert c["rule_id"] == EC.RULE_STANDALONE
    assert c["numeric_spans_raw"], case


def test_norm7_scientific_notation_kept_as_one_token():
    c = one_claim("Our model achieves an MAE of 1.2e-4 on the benchmark.")
    assert any("e-4" in t["text"] or "e-4" in t["text"].replace(" ", "")
               for t in c["numeric_spans_raw"]), c["numeric_spans_raw"]


def test_norm1_minus_sign_is_part_of_the_token():
    c = one_claim("Our model achieves −0.4 correlation on the benchmark.")
    assert any("−" in t["text"] for t in c["numeric_spans_raw"]), c["numeric_spans_raw"]


def test_times_ten_scientific_form():
    c = one_claim("The error was 1.2 × 10^-4 across all runs.")
    assert c["numeric_spans_raw"]


# ---- the required rejections ----------------------------------------------

def test_gpt4_based_metrics_is_number_in_name():
    assert only_reason("We evaluate with GPT-4-based metrics throughout.") \
        == EC.NUMBER_IN_NAME


def test_f1_score_is_number_in_name():
    assert only_reason("We report the F1 score for every configuration.") \
        == EC.NUMBER_IN_NAME


def test_table_2_is_number_is_label():
    assert only_reason("The full breakdown appears in Table 2 below.") \
        == EC.NUMBER_IS_LABEL


def test_bracket_citation_is_citation_marker():
    assert only_reason("This follows prior work [12] on the same dataset.") \
        == EC.CITATION_MARKER


def test_bracket_range_citation_is_citation_marker():
    assert only_reason("Several studies [3-5] report the same effect.") \
        == EC.CITATION_MARKER


def test_year_in_parens_is_year():
    assert only_reason("The approach of Smith and Jones (2021) is comparable.") \
        == EC.YEAR


def test_references_section_sentence_is_rejected():
    r = only_reason(
        "Doe, J. and Roe, R. Attention is all you need, pages 264-277, 2017.",
        section="references")
    assert r == EC.IN_REFERENCES


def test_no_number_sentence():
    assert only_reason("The proposed approach outperforms every baseline.") \
        == EC.NO_NUMBER


def test_table_block_is_rejected():
    assert only_reason("Ours 92.3 88.1 91.0 and more numbers here.",
                       block_type="table") == EC.IN_TABLE_BLOCK


def test_caption_is_rejected_by_block_type():
    assert only_reason("Accuracy of every model on the held-out split of 92.3.",
                       block_type="figure_caption") == EC.IN_CAPTION


def test_caption_is_rejected_by_opener():
    assert only_reason("Table 3: accuracy of every model, reaching 92.3 percent.") \
        == EC.IN_CAPTION


def test_acknowledgments_is_rejected():
    assert only_reason("This work was supported by grant 12345 from the agency.",
                       section="acknowledgments") == EC.IN_ACKNOWLEDGMENTS


# ---- mixed sentences: one standalone value is enough ----------------------

def test_label_plus_real_value_is_a_claim():
    c = one_claim("As Table 2 shows, our model reaches 92.3 accuracy.")
    kept = [t["text"] for t in c["numeric_spans_raw"]]
    assert "92.3" in kept
    assert "2" not in kept                      # the table label did not survive
    assert c["table_mentions_raw"] == ["Table 2"]


def test_citation_plus_real_value_is_a_claim():
    c = one_claim("Unlike prior work [12], we reach 92.3 accuracy overall.")
    assert [t["text"] for t in c["numeric_spans_raw"]] == ["92.3"]


def test_model_name_plus_real_value_is_a_claim():
    c = one_claim("Our ResNet-50 backbone reaches 92.3 accuracy on the split.")
    assert [t["text"] for t in c["numeric_spans_raw"]] == ["92.3"]


def test_bge_m3_alone_is_rejected():
    assert only_reason("We embed every chunk with bge-m3 in all experiments.") \
        == EC.NUMBER_IN_NAME


# ---- identity and spans ---------------------------------------------------

def test_claim_id_is_stable_and_span_derived():
    a = one_claim("Our model achieves 92.3 accuracy on the benchmark.")
    b = one_claim("Our model achieves 92.3 accuracy on the benchmark.")
    assert a["claim_id"] == b["claim_id"]
    assert a["claim_id"] == EC.claim_id("PID", tuple(a["char_span"]))


def test_char_span_is_absolute_to_the_block():
    c = one_claim("Our model achieves 92.3 accuracy on the benchmark.",
                  char_start=500)
    assert c["char_span"][0] >= 500


def test_numeric_span_points_at_the_number():
    text = "Our model achieves 92.3 accuracy on the benchmark."
    c = one_claim(text)
    s, e = c["numeric_spans_raw"][0]["span"]
    assert text[s:e].strip() == "92.3"


def test_overlapping_chunks_are_not_the_input():
    """Two blocks, not overlapping chunks: each sentence appears once."""
    blocks = [block("Our model reaches 92.3 accuracy.", char_start=0),
              block("The baseline reaches 88.1 accuracy.", char_start=100)]
    out = EC.extract("PID", blocks)
    assert len(out["claims"]) == 2
    assert len({c["claim_id"] for c in out["claims"]}) == 2


# ---- THE CONTRACT: STOP CONDITION 4 --------------------------------------

def test_record_is_a_dict_with_results_as_a_string():
    rec, _ = EC.claims_for_gate("PID", [block("Our model reaches 92.3 accuracy.")])
    assert isinstance(rec, dict)
    assert isinstance(rec["results"], str)
    assert rec["datasets"] is None and rec["metrics"] is None
    assert rec["paper_id"] == "PID"


def test_sent_round_trip_is_the_identity():
    """What gate_paper iterates must equal what the extractor emitted."""
    text = ("Our model reaches 92.3 accuracy. The baseline reaches 88.1 accuracy. "
            "Latency fell to 1.2e-4 seconds. See Table 2 for details. "
            "Prior work [12] reports less. Smith et al. (2021) differ.")
    rec, ex = EC.claims_for_gate("PID", [block(text)])
    emitted = [c["sentence"] for c in ex["claims"]]
    iterated = [s.strip() for s in _SENT.split(rec["results"].strip())
                if len(s.strip()) >= 12 and re.search(r"\d", s)]
    assert iterated == emitted, (iterated, emitted)


def test_round_trip_survives_an_unterminated_final_sentence():
    rec, ex = EC.claims_for_gate(
        "PID", [block("Our model reaches 92.3 accuracy"),      # no full stop
                block("The baseline reaches 88.1 accuracy", char_start=200)])
    emitted = [c["sentence"] for c in ex["claims"]]
    iterated = [s.strip() for s in _SENT.split(rec["results"].strip())
                if len(s.strip()) >= 12 and re.search(r"\d", s)]
    assert len(emitted) == 2
    assert iterated == emitted
    assert all(s.endswith(".") for s in emitted)


def test_empty_paper_yields_empty_blob():
    rec, ex = EC.claims_for_gate("PID", [])
    assert rec["results"] == "" and ex["claims"] == []


def test_every_emitted_sentence_passes_gate_paper_filters():
    text = ("Our model reaches 92.3 accuracy. Short 1. "
            "The baseline reaches 88.1 accuracy overall.")
    _rec, ex = EC.claims_for_gate("PID", [block(text)])
    for c in ex["claims"]:
        assert len(c["sentence"]) >= EC.MIN_SENTENCE_CHARS
        assert re.search(r"\d", c["sentence"])


# ---- STOP CONDITION 5 -----------------------------------------------------

def test_no_claim_ever_comes_from_references_table_or_caption():
    blocks = [
        block("Doe, J. Attention, pages 264-277, 2017.", section="references"),
        block("Ours 92.3 88.1 91.0 extra numbers.", block_type="table",
              char_start=100),
        block("Accuracy on the split was 92.3 overall.",
              block_type="figure_caption", char_start=200),
        block("Table 3: accuracy reaching 92.3 percent overall.", char_start=300),
        block("Our model reaches 92.3 accuracy.", char_start=400),
    ]
    out = EC.extract("PID", blocks)
    assert len(out["claims"]) == 1
    c = out["claims"][0]
    assert c["section"] == "results" and c["block_type"] == "paragraph"
    codes = {r["reason_code"] for r in out["rejections"]}
    assert codes == {EC.IN_REFERENCES, EC.IN_TABLE_BLOCK, EC.IN_CAPTION}
