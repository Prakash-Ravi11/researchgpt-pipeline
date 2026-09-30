# Repository inventory: ResearchGPT claim → table-cell binding (Phase 0)

| | |
|---|---|
| Repository root | `C:\Users\Praka\Downloads\researchgpt-pipeline` |
| Code under inventory | branch `claude-code-verification`, HEAD `30fc85d75d9ec5aaf8d354d38c0cddab82930418`. Working tree is clean under `src/`; untracked: `docs/`, `out/`, `src/evaluation/` |
| Date | 2026-09-29 |
| Mode | Read-only. Nothing was executed except read-only probes: `git`, file listings, hashes, an Ollama `GET /api/tags`, `nvidia-smi`, and `find_spec` on packages. No pipeline stage, test, LLM call or embedding was run. |

**Method.**
- The code was read in five passes:
  - four parallel read-only reader passes (pipeline stages; `src/evidence`; harnesses/tests/reports; branches/worktrees);
  - my own direct reading of `src/evidence/gate.py:200-715`, `src/evidence/anchors.py`, `src/processing/pdf_parser.py:150-205` and `src/evidence/represent.py:10-16,170-177`, plus the configs.
- Where the passes overlapped they agreed. The load-bearing claims in §0 were re-checked against source lines before writing.
- "*By reading*" marks behaviour inferred from code and not executed. It must be confirmed by an executed check in Phase 5/6 before anyone calls it a defect.
- RESEARCH_DIRECTIVE.md lists "multi-agent anything" as forbidden. I read that as a product-scope rule, not a rule about how the study itself is run. The four readers were read-only and changed nothing. Say so if you meant it differently.

---

## 0. The facts that shape the diagnosis

1. **The binder under test** is `structural_bind(value, chunks)` at `src/evidence/gate.py:390-493`. It is called only from `_gate_value` (`gate.py:526`), which `gate_paper` reaches at `gate.py:599,612`.
   - `src/evidence/` on HEAD is byte-identical to `09fbc95`, the fork point of all three experimental branches (`git diff --stat 09fbc95 HEAD -- src/evidence/` is empty).
2. **On HEAD, only JATS and LaTeX produce table cells.**
   - PDF table blocks carry none. The module docstring calls this "the bindability loss" (`represent.py:12-15`), and `blocks_from_pdf` only types a block `table` from its first line (`represent.py:172-176`).
   - With no cells, `structural_bind` returns `pdf_only` (`gate.py:432-434`), and the gate abstains with `unverifiable_binding` (`gate.py:528-531`). **That happens to every numeric claim on a PDF-only paper, whether or not it is correct.**
   - All 30 candidate-gold papers were acquired as PDF with `latex_ingestion=False`, and JATS was rejected (`rgpt-exp-parser:reproducibility/manifests/build_medical30_eval.py:8-14,229-233`).
3. **Production disables the whole evidence path.**
   - `evidence_grounding.enabled: false` (`configs/config.yaml:65`, `configs/config.example.yaml:69`). That flag gates the Stage-5 call (`src/summarization/summarize.py:1344-1346`), the grounded Stage-2 path (`pdf_parser.py:205-206,219-223`) and validated acquisition (`semantic_scholar.py:421-425`).
   - Only `configs/staging_config.yaml:62` enables it, and staging is also the only config with `temperature: 0` and `seed: 42` (`staging_config.yaml:29-30`; production has 0.2, `config.yaml:38`).
4. **Stage 4 produces no claim objects.**
   - The extraction schema has 10 keys (`summarize.py:539-544`). `results` is free prose and `metrics` holds metric *names*.
   - No value, subject, table, cell, page or chunk is carried, because the LLM is never shown locations (`summarize.py:824`).
   - The gate's "claims" are each `metrics` item plus each `results` sentence of at least 12 characters that contains a digit (`gate.py:592-612`).
5. **What the binder receives is very narrow.**
   - It gets only the claim string and a pooled, de-duplicated list of the paper's cells, each `{row_label, column_header, value, caption}` (`gate.py:273-284`).
   - There is **no table selection**: the claim's "Table N" is never used, and cells from all tables are pooled (`gate.py:432,453-454`).
   - It has no table_id, page, row/column index or header path.
6. **No gold-labelled binder oracle exists on HEAD.**
   - Positive controls are templated probes: binder-level `bound` on 4 of 5 canonical and 0 of 2 medical (artifact counts; §10.4).
   - **No numeric-coincidence negatives exist**: the probe builders deliberately exclude values that repeat (`binding_validation_measure.py:323-335`, `structural_binding_measure.py:173-180`, `gate_sensitivity.py:449`).
7. **A prior binding-diagnosis programme exists, but only on unmerged branches** (`exp/parser-backend`, `exp/r4-disambiguation`, `exp/stage-a`).
   - It was run on a 21-paper RAG-topic PDF subset with **0 overlap** with the 30 candidate papers.
   - Its last document ends with "corpus audit + gold set" as the next step (`exp/r4-disambiguation:docs/diagnosis/wrong_cell_review_v1.md:117-124`). §12 has the details.
8. **Where the 30 candidate PDFs are.**
   - They are untracked data in the sibling worktree `C:\Users\Praka\Downloads\rgpt-exp-parser` (branch `exp/r4-disambiguation`), under `data/medical30_eval/pdfs/`.
   - 29 of the 30 have **no Stage-2/3/4 output anywhere on disk**. P007 (`67d7236f…`) is the exception because it is also a medical50 paper (§13).
9. **Environment.**
   - The HEAD pipeline's dependencies are present: Ollama is reachable with `qwen2.5:7b`; torch sees CUDA on an RTX 3050 6 GB; `BAAI/bge-m3` is cached; `pymupdf`, `chromadb`, `sentence_transformers` and `pytest` are installed.
   - The experimental layout backend's `pymupdf4llm` is **absent** from the main `.venv`. The rgpt-exp-parser venv has it but lacks torch and chromadb.
10. **`experiments/EXP-LATEX-01/` does not exist.**
    - Checked: every branch's tree, every commit message, and the file names and contents of all three worktrees.
    - `src/evaluation/` is untracked on every branch, has no history (`git log --all -- src/evaluation` is empty), and holds only `candidate_gold/` plus three stale `.pyc` files from 2026-08-30 with no source anywhere.

---

## 1. Repository structure (relevant parts only)

| Path | What it is | Status |
|---|---|---|
| `run_pipeline.py` | CLI: Stage 1→2→3→4 then sanity check (`run_pipeline.py:26-57`) | tracked |
| `src/config.py` | YAML load, `S2_API_KEY` override, CUDA→CPU fallback (`src/config.py:22-44,47-63`) | tracked |
| `src/collection/semantic_scholar.py` | Stage 1 | tracked |
| `src/processing/pdf_parser.py`, `figure_extractor.py` | Stage 2, plus figures (API path only) | tracked |
| `src/embedding/build_index.py` | Stage 3 | tracked |
| `src/summarization/summarize.py`, `retrieval_aware.py` (+ maintenance CLIs) | Stage 4 | tracked |
| `src/evidence/` (12 modules, 2,922 lines) | representation, chunking, gate, binder, attribution | tracked; identical to `09fbc95` |
| `src/synthesis/`, `src/reporting/`, `src/orchestration/`, `src/api/` | synthesis/gaps (no table or binding logic), API orchestration | tracked, out of scope |
| `src/evaluation/` | `candidate_gold/…zip`, stale `__pycache__` (3 pyc), and this study's `bottleneck_diagnosis/` | **untracked** |
| `experiments/document_evidence_pipeline/` | measurement harnesses, reports, experiment-only `pipeline/`, unit suite `tests/test_pipeline_units.py`; `runs/` is gitignored (530 MB, 62 entries) | tracked except `runs/` |
| `reproducibility/` | manifests (canonical60, data_test8, medical50_frozen, medical50_reacquired), frozen artifacts, `verify_deterministic.py` | tracked |
| `tests/` | `test_anchors.py`, `test_pipeline.py`, `test_portability.py` | tracked |
| `configs/` | `config.yaml` and `test_config.yaml` (gitignored, local); `config.example.yaml`, `staging_config.yaml` (tracked) | mixed |
| `data/`, `data_test/` | live production corpus (50 papers, drifted) and staging corpus (8 papers) | gitignored |
| `docs/diagnosis/funnel_142_3_0.md`, `out/trace_on/*` | untracked copies of branch artifacts, byte-identical to blobs on `exp/parser-backend` / `exp/r4-disambiguation`, written at the `77dd6aa` run time (§12) | untracked |
| `frontend/`, `web/`, `backend/` | UI and auth; not part of this pipeline | out of scope |

`CLAUDE.md` points to `docs/ARCHITECTURE.md` and `docs/UI_SPEC.md`. Neither exists in this worktree; `docs/` holds only `diagnosis/funnel_142_3_0.md`.

## 2. Branches and worktrees

| Ref | Commit | Relation to HEAD | Checked out at |
|---|---|---|---|
| `claude-code-verification` (HEAD) = `phase7-portability` | `30fc85d` | — | main worktree |
| `exp/parser-backend` | `8f2140e` | forks at `09fbc95`; 16 ahead, 9 behind | — |
| `exp/r4-disambiguation` | `349a217` | parser-backend + 5 commits (`origin/…` is at `4fbf956`) | `C:\Users\Praka\Downloads\rgpt-exp-parser` |
| `exp/stage-a` | `078577f` | forks at `09fbc95`; shares parser-backend up to `92a7455`, plus 3 commits | `C:\Users\Praka\Downloads\rgpt-stage-a` |
| `ui/researchiq`, `master` | `cc58984`, older | UI work / old | — |

**Changes to `src/` on the experimental branches** (read from `git diff HEAD...<ref>`; nothing checked out):
- **Ownership policy** (`exp/parser-backend` and `exp/r4-disambiguation`):
  - An `evidence_grounding.ownership_policy` / `RGPT_OWNERSHIP_POLICY` switch.
  - `block` (the default, equal to HEAD) or `warn` (returns instead of abstaining on UNKNOWN attribution).
  - Location: `exp/parser-backend:src/evidence/gate.py:508-529,603-607`.
- **R4 scored disambiguation** (`exp/r4-disambiguation` only):
  - A `disambiguation_policy` / `RGPT_DISAMBIGUATION_POLICY` switch, default `legacy` = HEAD.
  - It fires only when at least 2 on-row cells match, and never fired on the measured corpus.
  - Location: `exp/r4-disambiguation:src/evidence/gate.py:468-612`.
- **Signed number comparator** (`exp/stage-a` only):
  - **Unflagged.** It changes the value comparator inside `structural_bind` (`exp/stage-a:src/evidence/gate.py:451,468-473`; `anchors.py:79-164`).
  - It changes matches in both directions: `4.1` vs `-4.1` no longer matches, while `15` vs `1,015` now matches.
  - It was measured with 0 status mismatches on its corpus.
- **Layout-aware PDF table cells** (all three branches): `src/evidence/represent_layout.py`, blob `93ac090`.
  - **Not wired into `build_document`.** It is called only by experiment harnesses (§12).

## 3. Pipeline stages on HEAD

| Stage | Entrypoint | Consumes → produces |
|---|---|---|
| 1 Collection | `run_collection` `src/collection/semantic_scholar.py:395-450`, or `re_acquire_corpus` `:453-494` when `collection.reacquire_existing` is set (no config sets it) | S2 search, then bge-m3 rerank (pool 100 → top 50, `config.yaml:6-7`) → `<raw_metadata_dir>/collected_papers.json` (`:445-447`) and `<pdf_dir>/{paperId}.pdf` (`:290-291`). The validated path also writes `.xml`/`.tex` and `acquisition_status`, `document_sha256` and related fields (`:279-281,339-385`). |
| 2 Processing | `run_processing` `src/processing/pdf_parser.py:202-243` | See §3.1 → `<processed_dir>/chunks.json` (`:237-240`) |
| 3 Embedding | `run_embedding` `src/embedding/build_index.py:151-170` | chunks → Chroma `PersistentClient(<chroma_dir>)`, collection `system.collection_name` (`researchgpt_papers`; staging `researchgpt_staging_papers`), deleted and recreated each run (`:89-101`); bge-m3, `max_seq_length` 1024, fp16 on CUDA (`:59-64`) |
| 4 Summarization | `run_summarization` `src/summarization/summarize.py:1280-1350` | selection (§3.3), then LLM extraction (§3.4) → `retrieval_selection.json`, `extraction_cache.json`, `paper_summaries.json` (`:1336-1337`), `clusters.json` (`:1348-1349`) |
| 5 Evidence gate (inside Stage 4) | `run_evidence_gate` `src/evidence/gate.py:629-715`, called at `summarize.py:1344-1346` **only if `evidence_grounding.enabled`** | rewrites `paper_summaries.json`; writes `paper_evidence.json`, `evidence_gate_summary.json`, `evidence_gate_range_rejections.json` (`gate.py:687-701`) and `evidence_monitor.json` (`monitor.py:99-102`) |
| Sanity check | `run_sanity_check` `sanity_check.py:156-177` | stdout only. It checks no gate output, and `run_all` returns True whatever it finds (`run_pipeline.py:57`) |

The API orchestration path (`src/orchestration/pipeline.py:45-122`) adds figure extraction, corpus synthesis and gap analysis, and has no sanity check. None of these touch tables or binding (`corpus_synthesis.py:1-13`, `gap_analysis.py:52-82`).

### 3.1 Stage 2: two paths, chosen by `evidence_grounding.enabled` (`pdf_parser.py:205-206,219-223`)
- **Legacy path (production).**
  - PyMuPDF `page.get_text()` joined across pages (`pdf_parser.py:32-39`); text truncated at references (`:22-24,44-46`).
  - 800-word windows with 100 overlap (`config.yaml:11-12`, `:54-83`).
  - Chunk fields: `{chunk_id, paper_id, title, year, venue, has_full_text, source, chunk_index, text}` (`:104-115`). **No page, section, block type or table.** Tables are never extracted.
- **Grounded path (staging).** `process_paper_grounded` (`pdf_parser.py:120-199`) calls `build_document` (`represent.py:424-460`), then `chunk_document` (`chunker.py:14-54`).
  - PDF: `get_text("blocks")` (`represent.py:151-153`). JATS: `xml.etree` (`:83-141`). LaTeX: `parse_latex_tables` (`:296-421`, off because `latex_ingestion_enabled: false`, `staging_config.yaml:69`).
  - Chunks are 220 words with 40 overlap, within a block (`chunker.py:10-11`).
  - Chunk fields add `representation, section, page_or_node, block_id, block_type, char_start, char_end`, and `table_cells` + `table_caption` when the block has them (`pdf_parser.py:174-198`).
  - LaTeX papers with a PDF twin must pass a strict parity gate (`latex_parity.py:95-131`, tolerance 0.0). If they fail, the whole paper falls back to PDF and all its cells are lost (`pdf_parser.py:158-167`).
  - The canonical document is **never persisted** (`pdf_parser.py:156-169`).

### 3.2 Stage 3: chunk metadata in Chroma
Each chunk carries `{paper_id, title, year, venue, has_full_text, source, chunk_index, section, page_or_node, block_id, representation}` (`build_index.py:103-122`). **Not carried:** `block_type`, `char_start/end`, `table_cells`, `table_caption`, or any table id.

### 3.3 Stage 4: selection (retrieval → delivered context)
- Selected by `summarization.context_selection: retrieval_aware` (`config.yaml:48`), calling `build_retrieval_aware_papers` (`summarize.py:1287-1291`). The budget is `llm.max_context_words` 2500 (`config.yaml:37`).
- **Legacy mode** (default, `retrieval_aware.py:47`):
  - 5 fixed queries, each `collection.query(n_results=50, where={"paper_id": pid})` (`:36-42,254-255`).
  - The union is ordered by `chunk_index` and truncated to budget (`:258-273`).
  - `n_results` was raised 3→50 in `2c7d0a9`; that value is frozen by the directive. The docstring still says top-3 (`:11-12`).
- **content_aware mode** (staging, `staging_config.yaml:42-45`): anchor/table-signal scoring, `max_passages` 10, `token_budget_chars` 9000 (`retrieval_aware.py:125-229`).
- Trace file: `<processed_dir>/retrieval_selection.json` (`:354-356`).

### 3.4 Stage 4: LLM extraction
- Ollama `/api/chat` with `format: json`, model `qwen2.5:7b` (`summarize.py:423-444`; `config.yaml:35-36`).
- User message: `Title + Text` only (`:824`).
- Prompts: `EXTRACTION_SYSTEM_PROMPT` (`:44-64`), or the biomedical variant (`:559-574`) chosen by cue counts (`:576-596`).
- Options:
  - `temperature` = `llm.temperature`, default 0.0 (`:833`).
  - `seed` is used only when `llm.seed` is set; it also pins `top_p` 0.9 / `top_k` 40 / `repeat_penalty` 1.1, forces 1 worker and enables priming (`:427-434,944-949`).
  - `num_ctx` is computed and clamped to [2048, 8192] (`:325-337`); `num_predict` 768; deadline 240 s.
- `system.seed` (42 in all configs) is **never read**. Retry tools force temperature ≥ 0.4 (`summarize.py:1418`, `fix_flagged_leakage.py:67`).
- Output: 10 keys (`:539-544`) plus diagnostic `_…` keys. Cache: `extraction_cache.json`, keyed by paper and valid only for the same `_prompt_version` and `_text_hash` (`:340-355,758-776`).

## 4. Table and cell representation

**Binder-side schema (HEAD, JATS/LaTeX only):**
- `schema.table_cell` (`schema.py:156-168`): `{value, column_header, row_label, caption, section, row, col, spans}`.
- `schema.structured_table` (`schema.py:122-153`): `{table_id, paper_id, source, representation, section, caption, n_cells, cells, raw_text, parse_status, fallback, notes}`.
- Only `table_cells` and `table_caption` reach the chunks (`chunker.py:47-52`); `table_id`, `parse_status`, `raw_text`, `fallback` and `notes` are dropped.

| Cell field | Exists? |
|---|---|
| row label / column header | yes: first cell of the row / **first header row only** (`latex_tables.py:287-291`; `represent.py:219`) |
| header hierarchy / path | **no** |
| raw text | no: `value` is cleaned text. The table-level `table_raw_text` exists for LaTeX only and is dropped by the chunker |
| normalized number, unit, sign, ± split | **no**: no float parsing in `represent`, `latex_tables` or `schema` |
| page, bbox | **no** (PyMuPDF coordinates are used only for sorting, `represent.py:152-153`) |
| table id / cell id | **not on the cell** |
| caption, section | yes |
| row/col index, spans | yes, but **`structural_bind` never reads them** |

**Front-ends that affect binding** (*by reading*, not yet executed):
- A two-level header puts the metric name into a data row, making the claim `not_bindable` (`latex_tables.py:287-313`; `represent.py:219-238`).
- Colspan may shift later cells to the right (`latex_tables.py:301-313`; `represent.py:230-238`).
- A multirow/rowspan label is lost on the rows after the first (`latex_tables.py:209-219,298`; `represent.py:213,225-238`).
- Leading minus signs are stripped from LaTeX values (`latex_tables.py:103`).
- `\pm` is kept as text.

**Candidate-gold comparison.** The candidate-gold cell schema (`candidate_gold_schema_report.md` §3) has `table_id`, `cell_id`, `row_index`, `column_index`, `raw_text`, `numeric_value`, `uncertainty` and `page` in addition to labels. The binder can consume only `row_label`, `column_header`, `value` and `caption`.

## 5. `structural_bind`: the binder (`gate.py:390-493`)

**Contract.**
- `value` is free-text claim text: a `metrics` item or one `results` sentence. It is reached only for those fields, and only when `_NUMVAL.search(value)` matches (`gate.py:516,525`).
- It reads only `chunk["table_cells"]`, and from each cell only `row_label`, `column_header`, `value` and `caption` (`gate.py:273-284,436-488`).
- `paper_table_cells` de-duplicates on `(row_label, column_header, str(value), caption)` (`:279-280`). This also merges identical cells from different tables that share a caption string.

**Decision order** (from code, `gate.py:432-493`). Steps 4-6 loop over the claim's numbers in order and **return on the first number that matches any cell**.

| # | status | condition |
|---|---|---|
| 1 | `pdf_only` (`structured: False`) | no cells in the paper |
| 2 | `no_number` | `NUMERIC_ANCHOR_RE.findall(value)` is empty (unreachable through the gate) |
| 3 | `not_bindable` | `_metric_tokens(value)` is empty, or no cell header shares a metric token |
| 4 | `bound` | the number is in a metric-column cell whose `row_label` matches the subject (first such cell) |
| 5 | `wrong_cell` | the number is in a metric-column cell, but not on the subject's row (`col_hits[0]`) |
| 6 | `wrong_cell` | the number is not in the metric column but is in some other cell (`elsewhere[0]`) |
| 7 | `not_a_table_claim` | none of the claim's numbers appears in any cell |

A `bound` result returns `{number, table_type, cell{row, col, value, caption}}`, with **no table_id and no indices** (`:436-440`).

| Sub-step | Implementation | Notes (*by reading* unless stated) |
|---|---|---|
| **Numbers** | `NUMERIC_ANCHOR_RE = \d+\.\d+\|\b\d{2,}\b` (`anchors.py:27`), via `findall` (`gate.py:442`) | Uses the **raw** regex, not `find_anchors` (`anchors.py:62-71`, which drops years, `[12]` citations, "Table N" and arXiv ids). So those numbers are tried too, in claim order. Signs and `%` are not captured; single digits never anchor. *(Verified directly.)* |
| **Metric identification** | `_metric_tokens` (`gate.py:294-319`): split on non-alphanumerics, intersect with `_METRIC_TOKENS` (39 tokens, `:32-38`), plus `_METRIC_NAME_RE` canonical names (`:96-118`); the same rule on claim and header | Generic tokens (`score`, `rate`, `error`, `loss`, `match`, `map`, `em`, `hit`, `exact`) count as metrics. No medical-specific names (ICC, PPV, NPV, HR, OR, C-index, ASSD, HD95…) are in `_METRIC_TOKENS`. |
| **Table selection** | **none**: all of the paper's cells are pooled | The claim's table reference is never used (also `exp/r4-disambiguation:diagnostics/funnel/STAGE_DEFINITIONS.md:289-295`) |
| **Column matching** | `_col_matches_metric` (`gate.py:322-327`) = the header's metric tokens intersected with the claim's | whole-token only |
| **Row matching** | `_row_matches_subject` (`gate.py:330-337`) | Subject comes from `_SUBJECT_RE` matched at the **start** of the claim (`:266-270,446-450`). No subject, or an own-work phrase, means implicit OWN, and the row must then match `_OWN_ROW` (`ours/proposed/our method/full/w/o/ablation…`, `:263-265`). Otherwise the subject and row must share a token, or the subject's first 12 alphanumerics must appear in the row. A row named only with the method's name fails OWN. "Dice of 94.9 …" makes the subject "Dice", giving a false `wrong_cell`. |
| **Cell matching** | `_has(n, s)` (`gate.py:459-465`): exact match after stripping `[^\d.\-]`, else the boundary regex `(?<![\d.])n(?![\d])` | No tolerance and no scale conversion (0.949 ≠ 94.9); `0.9` does not match `0.90`; `82.1 ± 0.3` matches both 82.1 and 0.3; `94` matches `94.9`; sign ignored |
| **Ties** | first match in pool order (`:473,475,484`) | no scoring and no ambiguous status. An earlier baseline number, count or year found in any cell decides the verdict (`wrong_cell`) before the real value is tried |
| **Table type** | `_table_type_for` → `classify_table` (`gate.py:362-387`) over all cells sharing the caption string | ablation cues win over results cues, which win over "other"; default is `results` if ≥1 metric header and ≥2 rows (the comment at `:377-378` says ≥2) |

## 6. Quality gate: `gate_paper` → `_gate_value` (`gate.py:586-620, 507-575`)

`gate_paper(record, chunks, acquisition_status, surnames)` reads `datasets`, `metrics` and `results`. `results` must be a string; a list is silently skipped (`:601-602`). Each item starts as ABSTAINED/MISSING (`:238-245`).

| Step | Applies to | Outcome, `abstain_reason` | Lines |
|---|---|---|---|
| acquisition_status ≠ `FULL_TEXT` | all | ABSTAINED `no_validated_full_text` | `:591-606` |
| sanity (digit, or a metric word of 4+ characters) | all | UNSUPPORTED `value_failed_sanity_check` | `:510-512,231-235` |
| metric range | metrics, results | UNSUPPORTED `metric_value_out_of_range` | `:516-521` |
| binding `pdf_only` | numeric metrics/results | UNSUPPORTED `unverifiable_binding` | `:528-531` |
| binding `wrong_cell` | same | UNSUPPORTED `binding_wrong_cell` | `:532-535` |
| `bound` to an ablation or "other" table | same | EXPLICIT, `provenance_valid=True`, **still ABSTAINED** `bound_to_{type}_table` | `:536-542` |
| grounding (`_ground`, text only; the bound cell is not used as the location) | all | UNSUPPORTED `evidence_span_not_found_in_paper_chunks` | `:547-551,190-228` |
| attribution CITED / UNKNOWN | metrics, results | ABSTAINED `attributed_to_cited_work` / `ownership_unverified` | `:560-573` |
| otherwise | — | RETURNED | `:574` |

- **Suppression after `bound`:** ablation/other table type; grounding failure; CITED or UNKNOWN attribution. `not_bindable` and `not_a_table_claim` fall through to grounding (`:543-546`).
- **On/off switches:**
  - Only `evidence_grounding.enabled` exists, and it turns off Stage 2 grounding and the gate together.
  - **No per-check flag exists.** Existing harnesses ablate a single check by replacing the module-level function: `structural_binding_measure.py:88-92`, `table_type_measure.py:69-81`, and `gate_sensitivity.py --no-range` at `:210-220`.
  - No environment variable affects the gate on HEAD.
- **Stage-2 parity gate:** described in §3.1 (`latex_parity.py:95-131`).

## 7. Attribution and provenance

- **Attribution.** `attribute_claim(context_text, evidence_span, …)` (`attribute.py:157-206`) escalates L1 sentence window → L2 chunk → L3 table/caption cues → L4 section subject → UNKNOWN. Confidence runs 0.6 → 0.3. The gate stores only `attribution` and `confidence` (`gate.py:566-567`).
  - *By reading:* the gate passes the **claim text** as `evidence_span` (`gate.py:561-562`). When the claim is not found verbatim, L1 scores the extractor's own wording (`attribute.py:88-100`).
- **Provenance.** It is copied from the grounded chunk: `source, representation, section, page_or_node, block_id, char_start, char_end` (`gate.py:553-557`).
  - `char_*` are the chunk's offsets, not the span's.
  - `provenance_valid=True` is set automatically, and nothing verifies it independently (`:558,540`).
  - On the grounded path, `source` is always overwritten to `full_text` (`pdf_parser.py:171-182`).
- **Unused modules.** `verifier.py` is an older field-presence checker with no pipeline caller (`src/evidence/__init__.py:10`, `verifier.py:150`). `schema.evidence_item` (`schema.py:80-98`) is unused.

## 8. Storage map (HEAD)

| Artifact | Path | Writer | On disk now |
|---|---|---|---|
| Paper metadata / acquisition | `<raw_metadata_dir>/collected_papers.json` | `semantic_scholar.py:445-447,493` | `data/` 50 papers (legacy Stage 1); `data_test/` 8 |
| Full text | `<pdf_dir>/{paperId}.pdf` (`.xml`/`.tex` on the validated path) | `semantic_scholar.py:290-291,339-342,374-376` | `data/pdfs` 130 PDFs |
| Parsed document / tables | **not persisted** (in memory in `pdf_parser.py:156-169`) | — | — |
| Evidence chunks | `<processed_dir>/chunks.json` | `pdf_parser.py:237-240` | `data/`: 489 legacy chunks, **0 with `table_cells`**; `data_test/`: 5,362 grounded chunks, **0 with `table_cells`** |
| Table metadata + cells | only inside `chunks.json` (`table_cells`, `table_caption`), grounded path only | `pdf_parser.py:193-196` | none anywhere in `data/` or `data_test/` |
| Vector index | `<chroma_dir>` | `build_index.py:85-135` | `data/chroma_db` (489 embeddings), `data_test/chroma_db` |
| Selection trace | `<processed_dir>/retrieval_selection.json` | `retrieval_aware.py:354-356` | yes |
| Extracted fields ("claims") | `<processed_dir>/paper_summaries.json` (rewritten in place by the gate); pre-gate values survive only in `extraction_cache.json` | `summarize.py:1336-1337`; `gate.py:687` | yes, dated 2026-09-11, **before** `2c7d0a9` (so `n_results=3`) |
| Structural-binding output | the `structural_binding` key on each item in `paper_evidence.json`. **No dedicated binding file**, and no binding-status counts in `evidence_gate_summary.json` | `gate.py:684-688` | only `data_test/` (5 items, all `pdf_only`) |
| Gate outputs | `paper_evidence.json`, `evidence_gate_summary.json`, `evidence_gate_range_rejections.json`, `evidence_monitor.json` | `gate.py:687-701`; `monitor.py:99-102` | only `data_test/`; the gate has never run on `data/` |
| Experiment results | `experiments/document_evidence_pipeline/runs/<name>/` (gitignored); 6 frozen copies in `reproducibility/artifacts/` | each harness | 62 entries, 530 MB |

## 9. Existing tests (identified; **not run**, since running them is Phase 5)

| File | Units | Binding / gate relevance | Needs | Command (Phase 5) |
|---|---|---|---|---|
| `experiments/document_evidence_pipeline/tests/test_pipeline_units.py` | 0 pytest tests; one `run()` with 64 `check()` sites, 63 executed | **26 binding/gate checks**: `gate:` (`:231-277`: pdf_only → unverifiable_binding `:252`, own cell → bound → RETURNED `:262`, cross-row → wrong_cell `:266`, not_a_table_claim `:273`, not_bindable `:277`); 11 symmetric-metric checks (`:293-328`); 4 adversarial (`:356-368`); 2 inv16 (`:386-388`). Also 12 attribution and 7 abstention checks | synthetic fixtures; optionally a cached PDF in the gitignored `pipeline/cache/` (32 present). No GPU, Ollama or network | `cd experiments\document_evidence_pipeline; ..\..\.venv\Scripts\python.exe -B -m tests.test_pipeline_units` (`reproducibility/README.md:215-217`) |
| `tests/test_anchors.py` | 9 | `NUMERIC_ANCHOR_RE` / `find_anchors`, the binder's number rule | pure | `.venv\Scripts\python.exe -B -m pytest -p no:cacheprovider tests/test_anchors.py -q` |
| `tests/test_pipeline.py` | 6 functions, 37 checks | chunking, cleaning, clustering; **nothing on binding**. Under pytest `check()` never asserts (`:26-36`) | numpy, `src` modules | run as a script to get a real exit code |
| `tests/test_portability.py` | 3 | device fallback, config, preflight; not binding | subprocess | `pytest tests/test_portability.py` |

- **No pytest configuration exists** anywhere.
- **No unit test exists for:**
  - `metric_range_check`;
  - `classify_table` and the `bound_to_{ablation,other}` withholding;
  - `structural_bind` case 6 (wrong column or cross-table);
  - first-match tie resolution.
- **Branch-only tests** exist but are not on HEAD: `test_represent_layout.py` (26), `test_explicit_claims.py` (30), `test_r4_disambiguation.py` (22), `test_claim_admission_v2.py` (20), `test_signed_anchors.py` (20), `tests/diagnostics/test_funnel_trace_noop.py` (11).

## 10. Existing measurement harnesses on HEAD

### 10.1 Binding-validation harness
- **Files:** `binding_validation_measure.py` (Tasks 1, 2, 3, 5), `gate_sensitivity.py --medical` (Task 4) and `binding_validation_invariants.py` (16 invariants) (`BINDING_VALIDATION_REPORT.md:14-16`).
- **Input:** medical50 re-acquired JATS papers (`runs/medical_reacquire/`: 12 pdf, 11 xml), with `staging_config.yaml` paths re-pointed (`binding_validation_measure.py:52-54,64-72`).
- **Dependencies:** Stage 2 if chunks are missing, BGE-M3 + Chroma, and Stage 4 via Ollama unless a cache exists (`:87-89,157-161,171-179`).
- **How it calls the gate:** real `gate_paper(rec, chunks, "FULL_TEXT", surnames)` (`:201`).
- **Probes:** templated as `"{row} reports a {metric} of {value} on the study cohort."` (`:319`).
- **Outputs:** `runs/binding_validation/*.json`.
- `binding_validation_invariants.py` **writes** `runs/binding_validation/invariants.json` (`:98`).

### 10.2 Gate-sensitivity harness (`gate_sensitivity.py`)
- **Calls** `_gate_value` directly (`:197-199`) on every RETURNED metrics/results item from canonical60, data_test and (with `--medical`) medical JATS (`:39-59,90-98`).
- **Mutants:** numeric perturbation, rule paraphrase, LLM paraphrase (Ollama, temperature 0, seed 42), fabrication, and two support-deletion types (`:232-308`).
- **Cross-row probe:** `_crossrow_probe` (`:427-463`).
- **`--no-range` ablation** (`:210-220`).
- **v2 oracle:** `_v2_oracle` (`:335-357`) **derives the expected verdict from the system-under-test's own `structural_bind`**, so it is not independent of the binder.
- **Inputs mix frozen and live data:** frozen staging evidence plus the live `data_test/processed/chunks.json` (`:44-47`).

### 10.3 Other harnesses
- **`structural_binding_measure.py` and `table_type_measure.py`:** Phase 5a-5c. They turn binding off and on by replacing `G.structural_bind` (`:88-92`; `:69-81`). Probe classes are `correct_cell`, `correct_row_wrong_col`, `correct_col_wrong_row` and `cross_table_substitution`. `correct_metric_wrong_condition` is named in the docstring but never built (`:6,170-182`).
- **`staging_run.py`:** full staging run plus 16 invariants. Invariants 7 and 8 share one predicate (`:246-247`). Invariant 15 lists statuses the binder no longer emits (`:230`).
- **Not relevant to the binder:** `extraction_fidelity.py`, `retrieval_recall.py` and `parity_gate_precision.py` are measurement harnesses that do not touch the binder. `runner.py` is a synthetic oracle that never calls the pipeline (`:1-5,86-92`).
- **`reproducibility/verify_deterministic.py`:** 36 exact checks over frozen artifacts, 11 of them binding checks (`:135-178`). **It rewrites the tracked `reproducibility/verify_results.json`** (`:215-218`).

### 10.4 Coverage relevant to Phases 6-7

| Capability | On HEAD? |
|---|---|
| Gold-labelled claim→cell oracle for `structural_bind` | **No** |
| Positive control (templated `correct_cell`) | Yes. Artifact counts: binder `bound` 4 of 5 canonical, 0 of 2 medical; gate RETURNED 1 of 5 and 0 of 2. 2 of the 7 controls use single-digit values that can never anchor |
| Cross-row negatives | yes (canonical 4 of 4, medical 2 of 2 caught) |
| Cross-column | probe class only (n = 3); no unit test |
| Wrong condition | medical only (n = 2) |
| Cross-table substitution | probe class only |
| **Numeric-coincidence negatives** | **No** (repeated values are deliberately excluded) |
| Gate on/off | whole gate by flag (production A/B); per check only by replacing the function |

## 11. Prior measured results on HEAD (quoted, **not re-verified**)

- **Structural binding never fires on real claims.** `bound` on 0 of 5 canonical and 0 of 2 medical returned claims: "the case-3 bind path is inert in production-realistic measurement" (`BINDING_VALIDATION_REPORT.md:161-168,290-292`; `CLAIM_LEDGER.md:46`). The report says this was "not chased" (`:95-96`).
  - The harness reader counted from `task2_binding.json` that the medical 0-of-2 has an effective binder denominator of 1.
- **Digits survive the PDF path, bindings do not.** 98.6% of values survive (lax) and 69.9% (strict), but only 16.8% stay context-bindable, and 8.9% for table values (`EXTRACTION_FIDELITY_REPORT.md:88-106`; `EXPERIMENT_MATRIX.md:92-95`).
- **Retrieval ranks well; selection drops the result.** R@10 = 0.940 while production delivery is 0.090 (0.071 on long papers) (`RETRIEVAL_RECALL_REPORT.md:78-90,110-122,200-214`). The 2,500-word assembly truncates 30 of 31 papers (`FINDINGS.md:48-61`).
- **The safety numbers hold by construction.** "false OWN = 0" and "provenance 100%" measure specificity only (`GATE_SENSITIVITY_REPORT.md:11-14`). Matrix C's "binding sensitivity 4/5" never exercises `bound` (`BINDING_VALIDATION_REPORT.md:237-246`).
- **No stage attribution exists yet.** No prior report attributes failures across parsing, retrieval, extraction and binding (`PHASE0_RECONCILIATION.md:131-137`).

## 12. Prior binding diagnosis on the experimental branches (quoted, **not re-verified**; different corpus)

**Corpus.** The 21 PDF-path papers of `runs/prodab-20260902T004416Z/canonical/`, a RAG topic (`exp/parser-backend:…/PARSER_BACKEND_REPORT.md:32-40`). **0 of these papers are among the 30 candidate papers.**

| Commit | Finding |
|---|---|
| `6b3eef7` | Layout backend `pymupdf4llm`: 92 tables / 2,187 cells, **bound 0 of 22 in every arm**. The cells were never checked against the PDFs. |
| `5f9ecf7` → withdrawn | "9 of 9 pdf_only are parser-side" was withdrawn: 3 are parser, 6 are the experiment's own quality gate. |
| `d3c139a` | Header-newline normalisation: prediction held, but still bound 0. It names three English-only blockers (`_METRIC_TOKENS`, attribution cues, table type "other"). |
| `aff29ba`/`92a7455` | Adjudication: **cell-literal ceiling 3 of 14, all 3 gate-blocked** (2 subject-match false rejections, 1 `∆` column with no metric token). |
| `77dd6aa` | Funnel: legacy claims 22 → 14 enter the binder → **0 bound**; defect "D3 NO_CLAIMS_REACH_BINDER". |
| `bd2121a` | Explicit rule-based claims: 2,218 → 1,754 enter → **5 bound**. |
| `8f2140e` | Among the 536 B-BIND failures, **NO_METRIC_IN_CLAIM is 414 (77.2%)**. |
| `5b290a9` | Row-subject acceptance fails 23 of 536 (4.3%). |
| `0cb3980` | Claim admission v2: 2,218 → 1,560 claims; binding residual unchanged. |
| `349a217` | WRONG_CELL residual 34, unlabelled. Rule: if no fixable cause covers ≥10 of 34, then "corpus audit + gold set". |

- **Status of that work.** No human labels exist in any labelling file, and every pre-registered decision rule is marked NOT APPLIED.
- **Metadata defect.** `run_funnel.py` records "from config" rather than the override flags actually used (`:605-609,688-697`).
- **Reusable harnesses** (branch-only):
  - `diagnostics/funnel/run_funnel.py` + `funnel_trace.py` (stage tracing that does not change results);
  - `classify_bindings.py` (7-way sub-reasons, re-implementing the **unsigned** `_has`);
  - `positive_control/run_positive_control.py` + `fixtures.json` (13 fixtures, L1 binder-only and L2 gate);
  - `measure_row_subject_acceptance.py`, `adjudication_set.py`, `explicit_claims.py` (claims without Stage 4);
  - `parser_backend_measure.py`: one process per paper × arm. Its loader needs `extraction_cache.json` + `reps.json`, which medical30 lacks, so an adapter would be needed.
- **Untracked copies in this worktree.** `docs/diagnosis/funnel_142_3_0.md` and `out/trace_on/*` are byte-identical to the branch blobs (the latter after CRLF normalisation). Their timestamps match the `77dd6aa` run.

## 13. The 30 candidate papers (`medical30_eval`)

- **Build script:** untracked, `rgpt-exp-parser:reproducibility/manifests/build_medical30_eval.py` (423 lines).
  - Query: "fetal brain MRI segmentation deep learning", 2019-2026, pool 200, target 30 (`:74-79`).
  - Download: `download_open_access_pdfs(validate=True, use_extra_sources=True, latex_ingestion=False)` (`:8-14,194-196`).
  - It accepts only the `pdf` representation (`:229-233`) and full text (`:51-71`).
  - The BGE-M3 rerank was skipped because torch is absent from that venv (`:19-22`).
  - **Its manifest target `reproducibility/manifests/medical30_eval.json` was never written.**
- **Data:** untracked, `rgpt-exp-parser/data/medical30_eval/`.
  - `pdfs/` holds 30 files, 146,062,324 bytes. The reader reports every sha256 equal to its recorded `document_sha256` (30 of 30); Phase 2 will recompute.
  - `_staging/` holds 70 files: 30 byte-identical copies, 7 other PDFs and 33 JATS `.xml` files, all rejected or not attempted.
  - `raw_metadata/collected_papers.json` has 30 records, all `pdf` / `FULL_TEXT`. Sources: arxiv 19, semantic_scholar 9, openalex 1, crossref 1.
- **Overlap with earlier corpora:** only P007 = `67d7236f524dae3bcf88b8f2726261d1acb5206b`, which is in medical50_frozen and medical50_reacquired with an identical sha256 prefix. It has Stage-3 chunks, Chroma entries and Stage-4 cache entries in `data/processed/` and `runs/binding_validation/`, `runs/medical_rechunk/`. **The other 29 have no Stage-2/3/4 output anywhere.**
- **Candidate-gold link:** each paper JSON's `source_filename` matches a `pdfs/` file stem (`candidate_gold_inventory.json` → `pdf_presence_preliminary`).

## 14. Environment (read-only probes, 2026-09-29)

| Item | Main `.venv` (Python 3.10.18) | `rgpt-exp-parser/.venv` |
|---|---|---|
| pymupdf / fitz | 1.28.2 | 1.28.2 |
| pymupdf4llm, pymupdf_layout (layout backend) | **absent** | 1.28.2 |
| torch (CUDA available: True) | 2.11.0+cu128 | absent |
| sentence_transformers / chromadb | 5.7.0 / 1.5.9 | absent |
| pytest | present | — |
| pdfplumber / camelot | absent | absent |

- **Ollama:** reachable at `localhost:11434`; models: `qwen2.5:7b`.
- **GPU:** NVIDIA GeForce RTX 3050 6 GB Laptop, driver 581.86.
- **Embedding model:** `BAAI/bge-m3` cached at `~/.cache/huggingface/hub/models--BAAI--bge-m3`.
- **No single venv can run the layout backend together with embeddings/Chroma.** Installing a dependency is a stop condition under RESEARCH_DIRECTIVE.md.

## 15. Hazards and constraints for later phases

1. **Scripts that write files.** `reproducibility/verify_deterministic.py` rewrites the tracked `reproducibility/verify_results.json`, and `binding_validation_invariants.py` overwrites `runs/binding_validation/invariants.json`. Neither may run in place during this study; run them on copies, or not at all.
2. **Stale baseline.** `data/processed/*` predates `2c7d0a9` (`n_results` 3→50), so it is not a HEAD baseline. `benchmark_canonical.py:46` reads the drifted live corpus.
3. **Staging paths.** `configs/staging_config.yaml` points at `data_test/`, and Chroma collections are deleted and recreated per run (`build_index.py:93-101`). Any pilot run needs its own config copy with isolated paths under `src/evaluation/bottleneck_diagnosis/`, so that no existing data or runs are overwritten.
4. **Gate output overwrites.** The gate rewrites `paper_summaries.json` in place. Pre-gate values survive only in `extraction_cache.json`.
5. **Binder output can only be compared by string.** A `bound` result carries strings only (row, col, value, caption), with no table_id or indices. Comparing against gold cells must match on strings.
6. **Credential hygiene.** An uncommitted literal Semantic Scholar API key sits in `rgpt-exp-parser/configs/staging_config.yaml:8` (value redacted; in no commit). Deciding whether to revert and rotate it is yours. It was not touched.
7. **Stray file removed.** One reader created the stray file `C:\WINDOWS\TEMP\_m30_ids_unused` (the 30 paper IDs) through a shell redirect. I inspected it and removed it. No other file in the repository or in the sibling worktrees was
   written. Transient reader outputs live only in the session scratchpad (outside the repository).

## 16. Decisions needed before Phase 2 and later

1. **Which code revision is "the current pipeline"?**
   - (a) HEAD `30fc85d`. Here the 30 PDF-only papers can never bind (§0.2); the end-to-end result is fixed by construction at Stage 2 representation.
   - (b) HEAD plus the branch-only `represent_layout.py` layout cells, as the existing experiments did. This also needs the venv question (§14) resolved.
   - (c) Both, reported separately.
2. **Which config?** Production disables the gate. Staging enables it (with temperature 0 and seed 42) but points at `data_test/`. A copy with isolated paths is needed either way.
3. **How to feed gold to the oracle (Phase 6).** `structural_bind` accepts only a claim string. It parses the subject from the string's start and the metric from a 39-token vocabulary, and pools every cell of the paper. There are two options, and they measure different things:
   - Pass verified gold claim sentences as they are (this measures the binder on real phrasing).
   - Build canonical `"<row> achieves <metric> of <value>"` strings from gold fields (this measures matching given perfect claim parsing).

## 17. Not read (stated, not inferred)

- **Reports** on HEAD: `ANCHOR_CENTRALIZATION_REPORT.md`, `DIAG_0549E2E9_REPORT.md`, `EXTRACTION_TRIAGE_REPORT.md`, `LATEX_ACQUISITION_REPORT.md`, `MEDICAL_REACQUIRE/RECHUNK/SELECTOR_CONTROL_REPORT.md`, `STAGE4_HARDENING_REPORT.md`, `progress.md`, `acquisition/*`.
- **FINAL_REPORT.md:** only greps and line ranges.
- **Harness bodies** of `eval_framework_*.py`, `production_ab.py`, `latex_ingestion_measure.py` and `medical_reacquire_measure.py`.
- **Branch files:** the bodies of branch test files; `run_funnel.py` probe bodies (`:91-369`); `positive_control_results.json`; and the `results*.json` of the parser-backend runs.
- **`src/evidence/acquire.py`**, and the body of `download_open_access_pdfs`: only the call sites.
- **Excluded by scope:** `frontend/`, `web/`, `backend/`, and the stale `src/evaluation/__pycache__/*.pyc` (not decompiled).
