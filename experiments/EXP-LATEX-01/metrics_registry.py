"""The metric family for EXP-LATEX-01, and how each metric may be tested.

Declaring the statistical treatment BEFORE any arm runs is the point of this
file: it pre-registers which test applies to which metric, so the choice cannot
be made after seeing which one gives a better p-value.

`kind` drives test selection (Part 13):
  continuous  -> paired t-test AND Wilcoxon signed-rank (both reported)
  binary      -> McNemar on paired per-paper outcomes
  proportion  -> per-paper rate; Wilcoxon + Wilson CI on the pooled rate
  count       -> Wilcoxon (counts are not normal at n=60)

`higher_is_better` fixes the direction of "improvement" up front.
`gate` is the Part-15 acceptance criterion where one was pre-specified.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Metric:
    key: str
    label: str
    group: str
    kind: str
    higher_is_better: bool
    gate: str | None = None
    note: str = ""


METRICS: tuple[Metric, ...] = (
    # A. acquisition
    Metric("acquisition_full_text", "Full-text acquisition", "A. Acquisition",
           "binary", True, note="per paper: FULL_TEXT reached"),
    Metric("acquisition_source_ok", "Source resolution success", "A. Acquisition",
           "binary", True),
    # B. structural extraction
    Metric("table_binding_rate", "Table binding (all table values)", "B. Structural",
           "proportion", True, gate=">= 0.089 (must not fall below baseline)"),
    Metric("table_binding_latex_eligible", "Table binding, LaTeX-eligible subset",
           "B. Structural", "proportion", True, gate=">= 0.60 (PRIMARY)"),
    Metric("table_completeness", "Table completeness (cells parsed / cells present)",
           "B. Structural", "proportion", True),
    Metric("row_col_preserved", "Row/column relation preserved", "B. Structural",
           "proportion", True),
    Metric("figure_association", "Figure-caption association", "B. Structural",
           "proportion", True),
    Metric("semantic_figures", "Semantic figures identified", "B. Structural",
           "count", True, note="NOT the embedded image-object count — see Part 18"),
    Metric("image_objects", "Embedded image objects", "B. Structural",
           "count", False, note="reported for contrast, not as a quality metric"),
    Metric("equation_preservation", "Equation preservation", "B. Structural",
           "proportion", True),
    Metric("anchor_delivery", "Section/anchor delivery", "B. Structural",
           "proportion", True, gate=">= 0.167"),
    # C. numeric fidelity
    Metric("numeric_survival_lax", "Numeric survival (verbatim-lax)", "C. Numeric",
           "proportion", True, gate=">= 0.980"),
    Metric("numeric_survival_strict", "Numeric survival (verbatim-strict)",
           "C. Numeric", "proportion", True),
    # D. evidence
    Metric("evidence_recall", "Evidence recall", "D. Evidence", "proportion", True),
    Metric("evidence_fields_nonempty", "Non-empty extracted fields / paper",
           "D. Evidence", "continuous", True,
           note="the Phase-4 headline regression metric (9.91 -> 5.82)"),
    # E. provenance
    Metric("provenance_valid", "Provenance validity", "E. Provenance",
           "proportion", True, gate="== 1.00"),
    # F. attribution
    Metric("wrong_paper_attrib", "Wrong-paper attributions", "F. Attribution",
           "count", False, gate="== 0"),
    Metric("false_own_paper", "False OWN_PAPER attributions", "F. Attribution",
           "count", False, gate="== 0"),
    # G. abstention
    Metric("abstention_correct", "Abstention correctness", "G. Abstention",
           "proportion", True, gate="== 1.00"),
    Metric("false_confident", "False confident answers", "G. Abstention",
           "count", False, gate="== 0"),
    # H. retrieval
    Metric("recall_at_10", "Recall@10", "H. Retrieval", "proportion", True),
    Metric("mrr", "MRR", "H. Retrieval", "continuous", True),
    Metric("ndcg_at_10", "nDCG@10", "H. Retrieval", "continuous", True),
    # I. runtime
    Metric("runtime_total_s", "Total runtime (s)", "I. Runtime", "continuous", False,
           gate="<= +50% vs control"),
    Metric("runtime_parse_s", "Parsing runtime (s)", "I. Runtime", "continuous", False),
    Metric("runtime_embed_s", "Embedding runtime (s)", "I. Runtime", "continuous", False),
    Metric("runtime_index_s", "Indexing runtime (s)", "I. Runtime", "continuous", False),
    # J. resources
    Metric("peak_vram_mib", "Peak VRAM (MiB)", "J. Resources", "continuous", False,
           gate="<= 5632 MiB (5.5 GB) preferred"),
    Metric("peak_ram_mib", "Peak RAM (MiB)", "J. Resources", "continuous", False),
    # chunking diagnostics (the secondary hypothesis)
    Metric("n_chunks", "Chunks per paper", "K. Chunking", "count", False),
    Metric("n_table_chunks", "Table chunks per paper", "K. Chunking", "count", False),
    Metric("tables_split", "Tables split across chunks", "K. Chunking", "count", False,
           note="the secondary hypothesis predicts 0 in the atomic arms"),
    Metric("tables_oversized", "Atomic tables above the chunk budget", "K. Chunking",
           "count", False),
)

BY_KEY = {m.key: m for m in METRICS}

#: Metrics that form the confirmatory family for multiple-comparison correction.
#: Everything else is exploratory and is labelled as such in the report.
CONFIRMATORY = (
    "table_binding_latex_eligible",
    "table_binding_rate",
    "numeric_survival_lax",
    "anchor_delivery",
    "evidence_fields_nonempty",
    "runtime_total_s",
)
