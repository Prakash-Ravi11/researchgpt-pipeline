"""
Unit tests for pipeline logic — synthetic edge cases, no external services.

Unlike sanity_check.py (which verifies your REAL pipeline's actual output),
these test the underlying functions directly with deliberately awkward
inputs, to catch bugs before they show up on real data 20 minutes into a run.

Run:
    python tests/test_pipeline.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np

from src.processing.pdf_parser import chunk_text, clean_text
from src.summarization.validate import stringify, listify, find_weak_extractions
from src.summarization.summarize import cluster_papers, should_attempt_dataset_fallback

PASS_COUNT = 0
FAIL_COUNT = 0


def check(label: str, condition: bool, detail: str = ""):
    global PASS_COUNT, FAIL_COUNT
    status = "PASS" if condition else "FAIL"
    if condition:
        PASS_COUNT += 1
    else:
        FAIL_COUNT += 1
    line = f"  [{status}] {label}"
    if detail and not condition:
        line += f" — {detail}"
    print(line)


def expect_raises(label: str, fn, *args, **kwargs):
    try:
        fn(*args, **kwargs)
        check(label, False, "expected an exception, none raised")
    except Exception:
        check(label, True)


# ---------------------------------------------------------------------------
# chunk_text
# ---------------------------------------------------------------------------

def test_chunk_text():
    print("\nchunk_text()")

    check("normal case produces multiple overlapping chunks",
          len(chunk_text(" ".join(["word"] * 1000), 800, 100)) == 2)

    check("short text produces exactly one chunk",
          len(chunk_text("just a few words here", 800, 100)) == 1)

    check("empty text produces zero chunks",
          chunk_text("", 800, 100) == [])

    check("whitespace-only text produces zero chunks",
          chunk_text("   \n\t  ", 800, 100) == [])

    check("exact chunk_size input produces exactly one chunk",
          len(chunk_text(" ".join(["word"] * 800), 800, 100)) == 1)

    # This is the bug we found by code review: overlap >= chunk_size used to
    # spin forever instead of failing. Confirm it now raises instead of hanging.
    expect_raises("overlap >= chunk_size raises instead of infinite-looping",
                  chunk_text, " ".join(["word"] * 2000), 100, 100)
    expect_raises("overlap > chunk_size raises instead of infinite-looping",
                  chunk_text, " ".join(["word"] * 2000), 100, 150)


# ---------------------------------------------------------------------------
# clean_text
# ---------------------------------------------------------------------------

def test_clean_text():
    print("\nclean_text()")

    text = "Some real content here.\n\nReferences\n[1] Some citation..."
    cleaned = clean_text(text)
    check("references section is cut off",
          "citation" not in cleaned.lower(), f"got: {cleaned!r}")
    check("content before references is kept",
          "real content" in cleaned)

    check("text with no references heading is left intact",
          "Just plain content, no back-matter." in clean_text("Just plain content, no back-matter."))

    check("collapses 3+ blank lines to 2",
          "\n\n\n\n" not in clean_text("a\n\n\n\nb"))

    check("empty input returns empty output",
          clean_text("") == "")


# ---------------------------------------------------------------------------
# stringify / listify (the type-coercion helpers that fixed the None/dict bug)
# ---------------------------------------------------------------------------

def test_stringify_listify():
    print("\nstringify() / listify()")

    check("stringify: plain string passes through",
          stringify("hello") == "hello")
    check("stringify: None becomes empty string",
          stringify(None) == "")
    check("stringify: dict is flattened to readable text",
          "technique" in stringify({"augmentation_technique": "style transfer"}))
    check("stringify: list is joined",
          stringify(["a", "b"]) == "a; b")
    check("stringify: nested dict-in-list doesn't crash",
          isinstance(stringify([{"k": "v"}, "plain"]), str))

    check("listify: plain list of strings passes through",
          listify(["a", "b"]) == ["a", "b"])
    check("listify: None becomes empty list",
          listify(None) == [])
    check("listify: single string becomes single-item list",
          listify("dataset X") == ["dataset X"])
    check("listify: empty string becomes empty list, not ['']",
          listify("") == [])
    check("listify: dict becomes list of key:value strings",
          len(listify({"a": 1, "b": 2})) == 2)
    check("listify: list containing a dict doesn't crash and stays a list",
          isinstance(listify([{"a": 1}, "plain"]), list))


# ---------------------------------------------------------------------------
# find_weak_extractions boundary conditions
# ---------------------------------------------------------------------------

def test_find_weak_extractions():
    print("\nfind_weak_extractions()")

    def record(summary="x", problem="x", method="x", findings="x", failed=False):
        return {
            "paper_id": "p", "summary": summary, "problem_addressed": problem,
            "method": method, "key_findings": findings, "_extraction_failed": failed,
        }

    check("all fields populated -> not weak",
          find_weak_extractions([record()]) == [])

    check("explicitly flagged _extraction_failed -> weak regardless of fields",
          find_weak_extractions([record(failed=True)]) == ["p"])

    check("exactly 3 of 4 fields empty -> weak (boundary, inclusive)",
          find_weak_extractions([record(problem="", method="", findings="")]) == ["p"])

    check("exactly 2 of 4 fields empty -> NOT weak (boundary, exclusive)",
          find_weak_extractions([record(problem="", method="")]) == [])

    check("all 4 fields empty -> weak",
          find_weak_extractions([record("", "", "", "")]) == ["p"])


# ---------------------------------------------------------------------------
# cluster_papers — the auto-k crash we found for small corpora
# ---------------------------------------------------------------------------

def test_cluster_papers_small_corpus():
    print("\ncluster_papers() on small corpora (the auto-k crash case)")

    rng = np.random.default_rng(42)

    for n in [2, 3, 4, 5, 9]:
        embeddings = {f"paper_{i}": rng.random(16) for i in range(n)}
        try:
            result, score = cluster_papers(embeddings, k="auto")
            ok = len(result) == n and all(pid in result for pid in embeddings)
            check(f"auto-k with n={n} papers doesn't crash and covers all papers", ok)
        except Exception as e:
            check(f"auto-k with n={n} papers doesn't crash and covers all papers", False, str(e))

    # Fixed k larger than paper count should clamp, not crash.
    embeddings = {f"paper_{i}": rng.random(16) for i in range(3)}
    try:
        result, score = cluster_papers(embeddings, k=6)
        check("fixed k=6 with only 3 papers clamps instead of crashing",
              len(result) == 3)
    except Exception as e:
        check("fixed k=6 with only 3 papers clamps instead of crashing", False, str(e))


def test_should_attempt_dataset_fallback():
    print("\nshould_attempt_dataset_fallback()")

    check("empirical study text triggers dataset fallback",
          should_attempt_dataset_fallback("We surveyed 200 participants and evaluated on the MNIST benchmark") is True)
    check("pure theory text does not trigger dataset fallback",
          should_attempt_dataset_fallback("This is a conceptual discussion of abstraction and proof-based reasoning") is False)
    check("empty text does not trigger dataset fallback",
          should_attempt_dataset_fallback("") is False)


# ---------------------------------------------------------------------------

def main():
            test_chunk_text()
            test_clean_text()
            test_stringify_listify()
            test_find_weak_extractions()
            test_cluster_papers_small_corpus()
            test_should_attempt_dataset_fallback()

            print(f"\n{'=' * 50}")
            print(f"{PASS_COUNT} passed, {FAIL_COUNT} failed")
            print("=" * 50)
            sys.exit(1 if FAIL_COUNT else 0)


if __name__ == "__main__":
    main()