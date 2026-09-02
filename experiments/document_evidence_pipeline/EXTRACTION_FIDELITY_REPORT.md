# EXTRACTION FIDELITY REPORT — PyMuPDF path vs structured full text

Branch `claude-code-verification` · HEAD `8ba6923` · 2026-09-02
Harness: `experiments/document_evidence_pipeline/extraction_fidelity.py`
Data: `runs/extraction_fidelity/{fidelity.json, pooled.json, eprint/*.tex}`
No change to the acquisition resolver or the evidence gate.

## Question

Does our real Stage-2 PDF path (PyMuPDF, `src/processing/pdf_parser.process_paper_grounded`) lose
meaningful numeric values — or their usable provenance/context — that a structured full text
(arXiv LaTeX source, Europe PMC JATS) preserves?

## STEP 1 — dual-representation set

Base set = the 34 validated full-text papers from acquisition run `20260901T165648Z-acqverify-3b2b`
(preserved PDFs in `runs/prodab-20260902T004416Z/canonical/pdfs/`). 24 came from arXiv, 2 from
Europe PMC (JATS), 8 from Semantic Scholar / OpenAlex (PDF only, no structured source available).

For the 24 arXiv papers we pulled the arXiv **e-print (LaTeX) source** (`https://arxiv.org/e-print/<id>`,
3 s politeness) and paired it with the PDF we already had.

| outcome | count | note |
|---|---|---|
| **arXiv PDF ↔ LaTeX pair, measured** | **23** | LaTeX has real `tabular` environments, `\caption`, `\label`, `\multicolumn` |
| arXiv, no LaTeX in e-print | 1 | `f1f07a37` (`2504.00698`) — PDF-only arXiv upload |
| Europe PMC JATS | 2 | `0549e2e9`, `f42ad6e2` — structured, but no paired PDF in our set → structured-side reference only |
| S2 / OpenAlex PDF | 8 | no structured source exists → not pairable |

**23 paired papers measured** — well above the target of 8.

## STEP 2 — numeric ground truth from the structured version

Every numeric token matching the number-anchored gate's rule (`\d+\.\d+ | \b\d{2,}\b`) was pulled from
each LaTeX / JATS source, with citation years, `\cite/\ref/\label/\includegraphics/\url` payloads, and
`arXiv:` ids excluded. Each value is tagged **table / caption / prose** by the LaTeX environment (or JATS
`<table-wrap>` / `<caption>`) it sits in, plus its section and ±140-char context.

Raw counts run 22–1,788 per paper (large ones are appendix result tables + per-example dumps). Because
"every ≥2-digit number in the source" also sweeps in hyperparameters, token counts, dollar figures and
model version strings, the headline is computed on a **meaningful subset** = values in a table/caption,
**or** prose values whose ±140-char context names a metric or a dataset. Total meaningful values across
the 23 papers: **6,530** (table 5,405 · caption 160 · prose 965).

## STEP 3 — survival through the real Stage-2 PDF path

Each paper's PDF was run through the actual pipeline function `process_paper_grounded` (the grounded
Stage-2 path the evidence gate consumes) **and** the legacy `process_paper` (800-word flat chunks, the
current production default). For every ground-truth value:

- **verbatim (lax)** — the digit string appears anywhere in the extracted chunk text.
- **verbatim (strict)** — the value appears in a chunk that also contains ≥1 four-letter word from the
  value's structured context (kills coincidental matches, e.g. a table cell `3.1` hitting "Section 3.1").
- **provenance** — that chunk carries a non-empty `section` and `page_or_node`.
- **context-bindable** — a metric or dataset word survives within ±90 chars of the value in the chunk,
  i.e. attribution could still tie the number to *what it measures* / *on what data*.

### Per-paper (meaningful subset)

| paper | n | strict verbatim | provenance | **bindable** | table n / vb / bind | prose n / vb / bind |
|---|---:|---:|---:|---:|---|---|
| 2009dbb5 | 45 | 1.00 | 1.00 | 0.16 | 35 / 1.00 / **0.00** | 8 / 1.00 / 0.75 |
| 4f3fca4c | 48 | 0.67 | 1.00 | 0.27 | 34 / 0.53 / 0.15 | 9 / 1.00 / 0.44 |
| f3b06a91 | 1472 | 0.24 | 1.00 | 0.02 | 1433 / 0.22 / 0.01 | 27 / 1.00 / 0.41 |
| fef0393e | 245 | 0.76 | 1.00 | 0.06 | 220 / 0.74 / 0.02 | 24 / 0.96 / 0.42 |
| eaec7401 | 229 | 0.97 | 1.00 | 0.18 | 159 / 1.00 / 0.03 | 57 / 0.90 / 0.49 |
| 413a184d | 1146 | 0.99 | 1.00 | 0.32 | 674 / 0.99 / 0.17 | 382 / 0.98 / 0.51 |
| e0efa866 | 483 | 0.98 | 1.00 | 0.07 | 477 / 0.98 / 0.07 | 3 / 1.00 / 0.33 |
| db78acdc | 128 | 1.00 | 1.00 | 0.31 | 98 / 1.00 / 0.16 | 30 / 1.00 / 0.80 |
| 93db4f9a | 158 | 0.99 | 1.00 | 0.38 | 88 / 0.99 / 0.17 | 63 / 1.00 / 0.67 |
| be7c4dc3 | 97 | 0.96 | 1.00 | 0.20 | 83 / 0.95 / 0.15 | 13 / 1.00 / 0.54 |
| 68f93a59 | 24 | 0.67 | 1.00 | 0.46 | 21 / 0.62 / 0.43 | 3 / 1.00 / 0.67 |
| d3b5f3c0 | 26 | 0.89 | 1.00 | 0.39 | 18 / 0.89 / 0.33 | 8 / 0.88 / 0.50 |
| f3d7e016 | 101 | 0.60 | 1.00 | 0.41 | 76 / 0.54 / 0.37 | 25 / 0.80 / 0.52 |
| 141276ba | 140 | 0.70 | 1.00 | 0.21 | 102 / 0.67 / 0.10 | 37 / 0.78 / 0.51 |
| ddb170b2 | 119 | 0.80 | 1.00 | 0.19 | 112 / 0.79 / 0.15 | 7 / 1.00 / 0.71 |
| 81e06066 | 22 | 0.95 | 1.00 | 0.23 | 11 / 0.91 / **0.00** | 9 / 1.00 / 0.56 |
| a9b2a3fd | 42 | 0.76 | 1.00 | 0.24 | 20 / 0.65 / **0.00** | 19 / 0.84 / 0.47 |
| cf099b7c | 788 | 0.53 | 1.00 | 0.07 | 711 / 0.48 / 0.02 | 65 / 0.97 / 0.59 |
| 96285d75 | 365 | 0.98 | 1.00 | 0.25 | 345 / 0.98 / 0.21 | 15 / 1.00 / 0.87 |
| 4d6e977f | 573 | 0.60 | 1.00 | 0.13 | 530 / 0.57 / 0.09 | 42 / 1.00 / 0.64 |
| a6d08e12 | 59 | 1.00 | 1.00 | 0.24 | 24 / 1.00 / **0.00** | 34 / 1.00 / 0.41 |
| 69b02cfe | 96 | 1.00 | 1.00 | 0.52 | 69 / 1.00 / 0.41 | 27 / 1.00 / 0.82 |
| 6437463b | 124 | 0.99 | 1.00 | 0.44 | 65 / 1.00 / 0.28 | 58 / 0.98 / 0.64 |

### POOLED (6,530 meaningful values, 23 papers) — the central numbers

| location | n | verbatim (lax) | verbatim (strict) | **provenance** | **context-bindable** | legacy-path verbatim |
|---|---:|---:|---:|---:|---:|---:|
| **all meaningful** | 6,530 | 98.6% | 69.9% | **100%** | **16.8%** | 67.3% |
| **table** | 5,405 | 98.7% | 64.3% | **100%** | **8.9%** | 61.9% |
| **caption** | 160 | 100% | 100% | 100% | 53.1% | 95.0% |
| **prose** | 965 | 98.2% | 96.6% | **100%** | **55.5%** | 92.8% |

Per-paper **median** (papers with ≥5 meaningful table values): table strict-verbatim **0.91**,
table context-bindable **0.14**, prose context-bindable **0.54**. Table-bindable per paper:
`[0.00, 0.00, 0.00, 0.00, 0.01, 0.02, 0.02, 0.03, 0.07, 0.09, 0.10, 0.14, 0.15, 0.15, 0.16, 0.17, 0.17, 0.21, 0.28, 0.33, 0.37, 0.41, 0.43]`
— **many papers at literally 0% for table values.**

### How many surviving values became unbindable

Of the ~4,566 pooled meaningful values that survive strict-verbatim (69.9% of 6,530), only ~1,097
(**24%**) are context-bindable; **~3,469 surviving values (76%) lost enough local context that
attribution could not tie them to a metric/dataset.** Almost all of that loss is in tables:
`table` drops from 3,476 strict-survivors to 481 bindable (**86% of surviving table values are
unbindable**); `prose` holds far better (931 → 536, 42% unbindable).

## STEP 4 — concrete collapsed-table structure (quoted from actual output)

**`4f3fca4c` — value `0.320`** (LaTeX: metric `R@500`, section *Results*)
```
LaTeX row : \textbf{Rewriting Strategy} & \textbf{R@500} \\ \midrule Original Query & 0.320 \\ Single R...
PDF chunk : Original Query 0.320 Single Rewrite 0.217 Multi Rewrite (3) 0.325 Multi Rewrite (10) 0.357 ...
            [section=results, page=p4]
```
Row labels ("Original Query") survive; the **`R@500` column header is gone from the local window** —
the row is a flat `label value label value …` run.

**`eaec7401` — value `69.87`** (LaTeX: `Model & Scenario & Higress & OpRAG & Impr. & Recall@5`)
```
PDF chunk : Llama3-8B Hybrid retrieval 69.87 28.21 59.62% 1.000 Llama3-8B LLM generation 217.41 103.30 ...
            [section=abstract, page=p9]
```
Six columns flattened to one number run. Is `69.87` the Higress or the OpRAG value? Unrecoverable.

**`413a184d` — value `100.00`** (LaTeX: `Category & $N$ & Recall@5 (\%) & Judge (\%)`)
```
PDF chunk : Dimensional 29 100.00 [100.0, 100.0] 79.31 [62.1, 93.1] Visual 16 87.50 [68.8, 100.0] ...
            [section=4.1. benchmark dataset construction, page=p10]
```
Headers detached; `100.00` now sits between `29` and a CI bracket with nothing naming it "Recall@5".

**`fef0393e` — value `2.3`** and **`f3b06a91` — value `10`**: the "verbatim hit" is a *false match* —
`2.3` matched "Section 2.3", `10` matched "≥1024 dimensions". The strict check flags these as
unbindable; they explain the gap between lax verbatim (98.7%) and strict (64.3%) for tables.

### Structured contrast (JATS)

`0549e2e9` (350 numeric values) and `f42ad6e2` (115) come to us as Europe PMC JATS. JATS keeps
`<table-wrap>` with `<thead>/<tbody>/<tr>/<td>`, so **every table cell stays bound to its column header
and row label by structure** — the collapse above simply does not happen. (These 2 have no paired PDF
in our set, so they are a reference point, not a survival measurement.)

## Verdict

**YES — PDF extraction is a measured bottleneck, specifically and only for table-resident quantitative
content.**

- The digits survive (≈99% lax verbatim) and **provenance survives 100%** (grounded Stage 2 always
  attaches section + page). Prose numbers keep their metric name (~55% bindable, ~97% strict-verbatim).
- **Table structure does not survive PyMuPDF.** ~9% pooled / ~14% median of table-resident meaningful
  values keep a metric/dataset label within ±90 chars; **86% of surviving table values are unbindable**.
  Multi-column result tables flatten to whitespace-separated number runs with headers and row labels
  detached, and coincidental digit collisions inflate any naïve verbatim measure.
- Because papers report most quantitative results in tables, this is the mechanism behind the evidence
  gate returning `results` mostly from prose/abstract sentences rather than result tables
  (`RESULTS_GATE_TUNING_REPORT.md`): the gate's number-anchor needs the metric token near the value in a
  chunk, and for table values PyMuPDF does not deliver that.
- The legacy flat-chunk path is marginally worse on verbatim and has **no provenance at all**.

## STEP 5 — arXiv LaTeX vs arXiv PDF: cheaper structural fix than a PDF library?

**Evidence FOR preferring arXiv LaTeX source:**
- **Coverage:** 24/34 (71%) of our full-text acquisition is arXiv; **23/24 of those shipped compilable
  LaTeX** with real `tabular` environments, `\caption`, `\label`, `\multicolumn`. LaTeX-first would give
  true table structure for **~68% of the full-text corpus (23/34)**.
- **Cost:** arXiv e-print is a plain HTTP GET + `tarfile`/`gzip` (stdlib) — **zero new dependency**.
  A LaTeX → structured-blocks converter is bounded work; pure-Python options exist (`pylatexenc`, MIT;
  `TexSoup`). No Java (GROBID / Tabula), no Ghostscript (Camelot), no per-page OCR/layout model.
- **Fidelity:** structural, deterministic, and strictly better than any PDF table extractor on the
  complex multi-column / `\multirow` / grouped-header tables that are exactly where PyMuPDF fails here.
- The 2 JATS papers already carry the same structure for free.

**Evidence AGAINST / limits:**
- It does **not** help the other ~32% — 8 S2/OpenAlex PDFs and 1 arXiv PDF-only upload still need the
  PDF path (or a PDF library). A PDF fallback stays required.
- LaTeX parsing has a long tail: custom `\newcommand` macros, `\input`/`\include` chains, `\csvreader`
  / programmatically generated tables, `siunitx` `\num{}` formatting, comments. A converter must be
  defensive; some tables will still degrade to prose.
- ~1/24 arXiv papers have no LaTeX; transient e-print download failures occur (1 in this run).
- Adds an arXiv fetch + untar to Stage 1 for arXiv papers (a few seconds each, politeness-limited).

**Net:** preferring arXiv LaTeX source over the arXiv PDF is the **cheaper structural improvement** —
it fixes the measured table-collapse bottleneck for roughly two-thirds of the full-text corpus with no
heavy dependency, whereas a PDF table-extraction library adds a large dependency and per-page runtime
for lower fidelity on the hard cases. It shrinks the PDF-extraction problem to ~1/3 of the corpus
rather than eliminating it. **Reported as evidence only; not implemented, per the task.**

---

### Reproduce

```
python experiments/document_evidence_pipeline/extraction_fidelity.py --step all   # step 1 fetches e-prints (~90s)
python experiments/document_evidence_pipeline/extraction_fidelity.py --step 3      # re-measure from cached sources
```
Artifacts: `runs/extraction_fidelity/fidelity.json` (per-value rows), `pooled.json`, `eprint/*.tex`.
Stage-2 measured via the real `src.processing.pdf_parser.process_paper_grounded` / `process_paper`.
