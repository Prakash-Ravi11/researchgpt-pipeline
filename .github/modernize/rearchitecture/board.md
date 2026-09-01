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

### ⏸ PAUSED — resume checklist in `experiments/document_evidence_pipeline/progress.md`

Stopped by user request (laptop offline overnight). Remaining: Phase 9 **paired production A/B**
(`python experiments/document_evidence_pipeline/production_ab.py --arm both`, ~100 min), Phase 10
quantitative sanity check, update the three reports, and the **final GO / GO_WITH_CHANGES / NOT_READY
decision based on the production A/B**. Current standing decision (from the isolated Level-3 A/B):
**GO_WITH_CHANGES**.
