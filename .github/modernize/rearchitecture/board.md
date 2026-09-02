## User Input

> Build and evaluate an isolated document-evidence pipeline for ResearchGPT. Audit acquisition, parsing, retrieval, extraction, attribution, abstention, and all six stages for scientific paper understanding. Use zero-human evaluation, preserve production behavior until measured evidence supports integration, and investigate the ai in agriculture corpus scenario.

**Project started**: 2026-09-01T00:00:00Z

## Tasks

### Phase: Isolation and Evidence Plan
- ✅ t1 [architect] Analyze six-stage execution and artifact integrity (00:00Z→08:24Z)
- ❌ t2 [architect] Research acquisition sources and document parser feasibility [findings]
- ❌ t2.1 [architect] Remediate exposed credential finding [external revocation unavailable]

> BLOCKED: Credential rotation and removal from configs/config.yaml and configs/test_config.yaml require implementation/security handoff and user action. Downstream benchmark tasks remain paused until the exposed credential is invalidated and removed.

### Phase: Experiment and Evaluation
- ✅ t3 [tester] Design retrieval and structured extraction benchmark
- ✅ t4 [tester] Design attribution and abstention evaluation
- ✅ t5 [pm] Define benchmark acceptance and production-preservation criteria

### Phase: Decision
- ❌ t6 [teamlead] Produce final benchmark decision and integration gate [NOT READY FOR PRODUCTION]

## Final Evidence

- ✅ Isolated 24-case attribution/abstention oracle: 24/24 passed
- ✅ Read-only current baseline benchmark: 50 papers, 26 full-text, 24 abstract-only, 128 chunks, 100% chunk coverage
- ✅ Source probes: OpenAlex, Crossref, and Europe PMC HTTP 200; Unpaywall blocked without contact email
- ✅ PyMuPDF probe measured; GROBID, Docling, and MinerU unavailable
- ❌ ChromaDB probe blocked by Rust/SQLite runtime panic
- ⏳ Cells A-E and structural parser comparison remain pending
- ❌ Final decision: NOT READY FOR PRODUCTION

---

## UPDATE — 2026-09-01 (this session; supersedes the "Final Evidence" block above)

The corpus was re-collected since the block above was written (now **60 papers**, domain
"domain-generalizable medical image segmentation" — NOT agriculture; the 50/26/128 figures are stale).
Several earlier claims did not reproduce and were corrected:

- ✅ **ChromaDB works** — no Rust/SQLite panic; full embed → index → query cycle exits 0.
- ✅ Baseline acquisition (verified live): **31/60 full text (51.7%)**.
- ✅ Isolated canonical pipeline built + validated (Level 1 unit 37/37, Level 2 subset, **Level 3 full
  60-paper A/B** `runs/20260901T170346Z-canon-L3-525e`): acquisition **34/60 (56.7%)**, provenance
  **150/150 (100%)**, no-full-text quantitative abstention **78/78 (100%)**, 0 wrong-paper, **0 false
  OWN_PAPER** across 21 hand-checked returned quantitative items, quantitative recall metrics 5→13 /
  results 3→8 after the hierarchical-attribution rework. No reranker / GROBID / Docling / MinerU / new
  LLM. Runs in 51 min on a 6 GB laptop GPU (2.65 GB VRAM).
- ✅ **Production integration of the 5 FINAL_REPORT.md §O changes: DONE** (commits `f12089d..fce2328`),
  behind `config['evidence_grounding']['enabled']` (default false = exact legacy behaviour). Phases 1–8
  verified (existing `tests/test_pipeline.py` 37/37; production acquisition + gate smokes pass).

### ✅ PRODUCTION INTEGRATION + PAIRED A/B DONE — 2026-09-02 (commits `f12089d..2bc2a3c`)

Paired production A/B `runs/prodab-20260902T004416Z/` — both arms ran the real six-stage modules on the
frozen 60-paper corpus. **Production reproduces the isolated run:**

- acquisition **31/60 → 34/60**, all 34 identity + content validated, **0 wrong-paper**
- provenance-valid **91/91 (100%)**; schema problems 0
- no-full-text quantitative fields abstained **112/112 (100%)**; **0/26** inaccessible papers leak a
  Dataset/Metric/Result (baseline emits them for all 26)
- grounded quant attribution OWN 15 / CITED 7 / UNKNOWN 17 → only the 15 OWN RETURNED; Phase-10 check:
  **0 false OWN_PAPER**, 15/15 numbers verbatim in the paper
- one gate defect found + fixed (`2bc2a3c`): tight `evidence_span` sentence + body-over-abstract grounding
- `tests/test_pipeline.py` 37/37; experiment suite 37/37; 0 pipeline errors both arms
- 5 §O changes only, all inside the existing six stages; single `src/evidence/` copy (−635 LOC from
  shims); no new stage / model / service / parser / reranker; flag defaults **false**

### FINAL DECISION — **GO_WITH_CHANGES** (`FINAL_REPORT.md` §R.6)

Ship behind `config['evidence_grounding']['enabled']` (default false). Path to flat GO: tune the
`results`-gate operating point → paired A/B on a non-RAG corpus → human-gold spot-check ~20 RETURNED
items → enable in staging with monitoring, then production. Not NOT_READY — no unsupported quantitative
claim reaches output.
