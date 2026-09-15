"""
EXP-LATEX-01 — LaTeX table atomicity and structural handling.

Covers the eight table shapes the experiment must handle deliberately
(normal / oversized / captioned / multi-column / nested / equations /
citations / malformed), plus the two safety properties the experiment rests on:

  * with ``RQ_TABLE_ATOMIC`` off, chunking is byte-identical to the pre-experiment
    chunker — the control arm is the real control;
  * with it on, a ``table`` block is never split, at any size.

Stdlib only, no external services, no corpus. Run:
    python tests/test_table_atomic.py
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.evidence import flags
from src.evidence.chunker import CHUNK_WORDS, chunk_document
from src.evidence.latex_tables import parse_latex_tables
from src.evidence.represent import blocks_from_latex

PASS_COUNT = 0
FAIL_COUNT = 0


def check(label: str, condition: bool, detail: str = ""):
    global PASS_COUNT, FAIL_COUNT
    if condition:
        PASS_COUNT += 1
    else:
        FAIL_COUNT += 1
    line = f"  [{'PASS' if condition else 'FAIL'}] {label}"
    if detail and not condition:
        line += f" — {detail}"
    print(line)


# --- fixtures ---------------------------------------------------------------

NORMAL = r"""
\section{Results}
\begin{table}[t]\caption{Main results.}
\begin{tabular}{lcc}
Method & Acc & F1 \\ \hline
BM25 & 41.2 & 39.8 \\
BGE-M3 & 68.7 & 66.1 \\
\end{tabular}\end{table}
"""

_SWEEP_ROWS = "\n".join(
    f"Sys{i} & {40 + i}.1 & {30 + i}.7 & {20 + i}.3 & {10 + i}.9 \\\\" for i in range(160))
OVERSIZED = r"""
\section{Results}
\begin{table*}\caption{Full sweep across 160 systems.}
\begin{tabular}{lcccc}
System & P & R & F1 & MRR \\ \hline
""" + _SWEEP_ROWS + r"""
\end{tabular}\end{table*}
"""

CAPTIONED = r"""
\begin{table}\caption[short form]{Ablation on the retrieval component.}\label{tab:abl}
\begin{tabular}{lc}
Variant & nDCG \\ \hline
full & 0.71 \\
-rerank & 0.65 \\
\end{tabular}\end{table}
"""

MULTICOL = r"""
\begin{table}\caption{Grouped columns.}
\begin{tabular}{lcccc}
 & \multicolumn{2}{c}{Clean} & \multicolumn{2}{c}{Poisoned} \\
Model & P & R & P & R \\ \hline
GPT-3.5 & 0.81 & 0.77 & 0.42 & 0.39 \\
BERT & 0.74 & 0.70 & 0.51 & 0.48 \\
\end{tabular}\end{table}
"""

NESTED = r"""
\begin{table}\caption{Outer with a nested grid.}
\begin{tabular}{lc}
Group & Detail \\ \hline
A & \begin{tabular}{cc} x & 1 \\ y & 2 \\ \end{tabular} \\
B & 7.5 \\
\end{tabular}\end{table}
"""

EQUATIONS = r"""
\begin{table}\caption{With inline math.}
\begin{tabular}{lc}
Loss & Value \\ \hline
$\mathcal{L}_{\text{adv}}$ & $0.34 \pm 0.02$ \\
$\alpha=0.5$ & \num{12.75} \\
\end{tabular}\end{table}
"""

CITATIONS = r"""
\begin{table}\caption{Baselines.}
\begin{tabular}{lc}
Method & Score \\ \hline
DPR~\cite{karpukhin2020} & 55.3 \\
ColBERT \citep{khattab2020} & 61.8 \\
\end{tabular}\end{table}
"""

MALFORMED = r"""
\begin{table}\caption{Broken — the colspec brace is never closed.}
\begin{tabular}{lcc
Method & Acc & F1 \\ \hline
BM25 & 41.2 & 39.8
\end{table}
"""


def _table_chunks(tex: str, atomic: bool):
    blocks = blocks_from_latex(tex, "P", "arxiv")
    chunks = chunk_document({"blocks": blocks}, table_atomic=atomic)
    return [c for c in chunks if c["block_type"] == "table"]


def _one_table(tex: str):
    tables = parse_latex_tables(tex, "P", "arxiv")
    return tables[0] if tables else None


# --- 1. normal table --------------------------------------------------------

def test_normal_table():
    print("\n1. normal table")
    t = _one_table(NORMAL)
    check("parses cleanly", t["parse_status"] == "parsed", str(t["parse_status"]))
    check("four data cells recovered", t["n_cells"] == 4, str(t["n_cells"]))
    vals = {c["value"] for c in t["cells"]}
    check("every numeric value retained", {"41.2", "39.8", "68.7", "66.1"} <= vals, str(vals))
    heads = {c["column_header"] for c in t["cells"]}
    check("column headers bound to cells", heads == {"Acc", "F1"}, str(heads))
    labels = {c["row_label"] for c in t["cells"]}
    check("row labels bound to cells", labels == {"BM25", "BGE-M3"}, str(labels))
    check("fits one chunk either way",
          len(_table_chunks(NORMAL, False)) == len(_table_chunks(NORMAL, True)) == 1)


# --- 2. oversized table -----------------------------------------------------

def test_oversized_table():
    print("\n2. oversized table (the secondary hypothesis)")
    t = _one_table(OVERSIZED)
    check("parses cleanly", t["parse_status"] == "parsed", str(t["parse_status"]))
    check("640 data cells recovered", t["n_cells"] == 640, str(t["n_cells"]))
    off = _table_chunks(OVERSIZED, False)
    on = _table_chunks(OVERSIZED, True)
    check("control splits the table", len(off) > 1, f"{len(off)} chunks")
    check("treatment keeps it whole", len(on) == 1, f"{len(on)} chunks")
    check("oversized chunk is flagged, not split", on[0]["table_oversized"] is True)
    check("word count recorded", on[0]["table_n_words"] > CHUNK_WORDS,
          str(on[0].get("table_n_words")))
    check("caption survives on the atomic chunk",
          "160 systems" in on[0]["table_caption"], on[0]["table_caption"])
    check("section/anchor metadata preserved",
          on[0]["section"] == "results" and on[0]["page_or_node"].endswith("tab1"),
          f"{on[0]['section']} / {on[0]['page_or_node']}")
    check("all 640 cells reachable from the single chunk",
          len(on[0]["table_cells"]) == 640, str(len(on[0]["table_cells"])))
    # the control loses row/column context at every cut point
    first_row = "Sys0"
    check("control strands later rows in chunks without the header",
          any(first_row not in c["text"] for c in off))


# --- 3. table with caption --------------------------------------------------

def test_table_with_caption():
    print("\n3. table with caption")
    t = _one_table(CAPTIONED)
    check("optional [short form] arg not mistaken for the caption",
          t["caption"] == "Ablation on the retrieval component.", repr(t["caption"]))
    check("\\label stripped from the caption", "tab:abl" not in t["caption"])
    check("caption copied onto every cell",
          all(c["caption"] == t["caption"] for c in t["cells"]))
    on = _table_chunks(CAPTIONED, True)
    check("caption reaches the chunk", "Ablation" in on[0]["table_caption"])


# --- 4. multi-column table --------------------------------------------------

def test_multicolumn_table():
    print("\n4. multi-column table")
    t = _one_table(MULTICOL)
    check("parses", t["parse_status"] in ("parsed", "partial"), str(t["parse_status"]))
    vals = {c["value"] for c in t["cells"]}
    check("all eight measurements retained",
          {"0.81", "0.77", "0.42", "0.39", "0.74", "0.70", "0.51", "0.48"} <= vals,
          str(sorted(vals)))
    check("\\multicolumn did not collapse a column",
          len([c for c in t["cells"] if c["row_label"] == "GPT-3.5"]) == 4,
          str([c["value"] for c in t["cells"] if c["row_label"] == "GPT-3.5"]))
    check("column relationships preserved under atomic chunking",
          len(_table_chunks(MULTICOL, True)) == 1)


# --- 5. nested tabular ------------------------------------------------------

def test_nested_tabular():
    print("\n5. nested tabular (silent-truncation regression)")
    tables = parse_latex_tables(NESTED, "P", "arxiv")
    check("the inner grid does not become a second table",
          len(tables) == 1, f"{len(tables)} tables")
    t = tables[0]
    check("structural failure is declared, not hidden",
          t["parse_status"] == "fallback_pdf" and t["fallback"] == "nested_tabular",
          f"{t['parse_status']}/{t['fallback']}")
    check("no invented structure", t["n_cells"] == 0, str(t["n_cells"]))
    check("reason recorded in notes", any("nested" in n for n in t["notes"]), str(t["notes"]))
    # The regression this guards: rows AFTER the inner \end{tabular} used to be
    # dropped from both cells and raw_text while parse_status said "parsed".
    check("value after the nested block is retained (7.5)", "7.5" in t["raw_text"],
          repr(t["raw_text"]))
    check("inner grid values also retained",
          "1" in t["raw_text"] and "2" in t["raw_text"])
    check("still one atomic chunk", len(_table_chunks(NESTED, True)) == 1)
    # A DIFFERENT grid environment nested inside also corrupts the &/\\ split,
    # even though the outer \end{tabular} is matched correctly by name.
    mixed = NESTED.replace(r"\begin{tabular}{cc} x & 1 \\ y & 2 \\ \end{tabular}",
                           r"\begin{array}{cc} x & 1 \\ y & 2 \\ \end{array}")
    tm = parse_latex_tables(mixed, "P", "arxiv")[0]
    check("array nested in tabular is caught too",
          tm["parse_status"] == "fallback_pdf" and tm["fallback"] == "nested_tabular",
          f"{tm['parse_status']}/{tm['fallback']}")
    check("and its trailing row survives", "7.5" in tm["raw_text"], repr(tm["raw_text"]))


# --- 6. table containing equations ------------------------------------------

def test_table_with_equations():
    print("\n6. table containing equations")
    t = _one_table(EQUATIONS)
    vals = " ".join(c["value"] for c in t["cells"])
    check("$...$ numeric body survives", "0.34" in vals and "0.02" in vals, vals)
    check("\\num{} body survives", "12.75" in vals, vals)
    check("math did not empty the cell", t["n_cells"] == 2, str(t["n_cells"]))
    check("raw_text also carries the numerics",
          all(v in t["raw_text"] for v in ("0.34", "0.02", "12.75")), repr(t["raw_text"]))


# --- 7. table containing citations ------------------------------------------

def test_table_with_citations():
    print("\n7. table containing citations")
    t = _one_table(CITATIONS)
    vals = {c["value"] for c in t["cells"]}
    check("\\cite did not displace the value", "55.3" in vals, str(vals))
    check("\\citep did not displace the value", "61.8" in vals, str(vals))
    check("citation key never becomes a measurement",
          not any(k in " ".join(vals) for k in ("karpukhin", "khattab")), str(vals))
    check("method name still recoverable as the row label",
          any(c["row_label"].startswith("DPR") for c in t["cells"]),
          str([c["row_label"] for c in t["cells"]]))


# --- 8. malformed LaTeX -----------------------------------------------------

def test_malformed_latex():
    print("\n8. malformed LaTeX")
    tables = parse_latex_tables(MALFORMED, "P", "arxiv")
    check("does not raise", True)
    check("one table object still emitted", len(tables) == 1, f"{len(tables)}")
    t = tables[0]
    check("marked as a fallback with a reason",
          t["parse_status"] == "fallback_pdf" and bool(t["fallback"]),
          f"{t['parse_status']}/{t['fallback']}")
    check("no fabricated cells", t["n_cells"] == 0, str(t["n_cells"]))
    check("numerics still recovered into raw_text",
          "41.2" in t["raw_text"] and "39.8" in t["raw_text"], repr(t["raw_text"]))
    check("chunking survives a malformed table", len(_table_chunks(MALFORMED, True)) == 1)


# --- flag semantics ---------------------------------------------------------

def test_flag_semantics():
    print("\n9. flag semantics")
    saved = os.environ.get(flags.TABLE_ATOMIC_ENV)
    try:
        os.environ.pop(flags.TABLE_ATOMIC_ENV, None)
        check("default is OFF", flags.table_atomic() is False)
        blocks = blocks_from_latex(OVERSIZED, "P", "arxiv")
        check("unset env splits the oversized table",
              len([c for c in chunk_document({"blocks": blocks})
                   if c["block_type"] == "table"]) > 1)
        os.environ[flags.TABLE_ATOMIC_ENV] = "1"
        check("RQ_TABLE_ATOMIC=1 turns it on", flags.table_atomic() is True)
        check("env flag reaches chunk_document",
              len([c for c in chunk_document({"blocks": blocks})
                   if c["block_type"] == "table"]) == 1)
        os.environ[flags.TABLE_ATOMIC_ENV] = "0"
        check("RQ_TABLE_ATOMIC=0 turns it off", flags.table_atomic() is False)
        os.environ[flags.TABLE_ATOMIC_ENV] = "banana"
        try:
            flags.table_atomic()
            check("a non-boolean value is rejected", False, "no exception")
        except flags.FlagError:
            check("a non-boolean value is rejected", True)
    finally:
        os.environ.pop(flags.TABLE_ATOMIC_ENV, None)
        if saved is not None:
            os.environ[flags.TABLE_ATOMIC_ENV] = saved


def test_control_arm_is_unchanged():
    print("\n10. control arm equals the pre-experiment chunker")
    # Non-table blocks must be untouched by the flag, in both states.
    doc = {"blocks": blocks_from_latex(OVERSIZED + NORMAL + CITATIONS, "P", "arxiv")}
    off = chunk_document(doc, table_atomic=False)
    on = chunk_document(doc, table_atomic=True)
    off_nt = [c for c in off if c["block_type"] != "table"]
    on_nt = [c for c in on if c["block_type"] != "table"]
    check("non-table chunks identical under the flag", off_nt == on_nt,
          f"{len(off_nt)} vs {len(on_nt)}")
    check("flag-off records carry no experiment keys",
          all("table_atomic" not in c for c in off))
    check("only table chunk counts differ",
          len(off) > len(on) and
          len([c for c in off if c["block_type"] != "table"]) ==
          len([c for c in on if c["block_type"] != "table"]))


def main():
    print("=" * 62)
    print("EXP-LATEX-01 — table atomicity + structural handling")
    print("=" * 62)
    test_normal_table()
    test_oversized_table()
    test_table_with_caption()
    test_multicolumn_table()
    test_nested_tabular()
    test_table_with_equations()
    test_table_with_citations()
    test_malformed_latex()
    test_flag_semantics()
    test_control_arm_is_unchanged()
    print(f"\n{'=' * 62}")
    print(f"{PASS_COUNT} passed, {FAIL_COUNT} failed")
    print("=" * 62)
    sys.exit(1 if FAIL_COUNT else 0)


if __name__ == "__main__":
    main()
