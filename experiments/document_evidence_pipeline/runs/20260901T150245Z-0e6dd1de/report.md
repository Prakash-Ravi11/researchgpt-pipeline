# Document Evidence Baseline (20260901T150245Z-0e6dd1de)

Decision: **NOT READY**

## Baseline
- Papers: 60
- PDFs: 249
- Chunks: 304
- Weak extractions: 1
- Chunk coverage: 1.0
- Deterministic verifier: {'status': 'measured', 'case_count': 24, 'passed': 24, 'failed': 0, 'citation_validity': 0.9583333333333334, 'abstention_precision': 1.0, 'cited_paper_false_own_rate': 0.0, 'provenance_valid_rate': 0.9583333333333334}
- Stage ID consistency: {'status': 'measured', 'artifact_id_counts': {'raw_metadata': 60, 'chunks': 60, 'summaries': 60, 'weak_extractions': 0}, 'union_id_count': 60, 'intersection_id_count': 60, 'ids_not_shared_by_all': {'raw_metadata': 0, 'chunks': 0, 'summaries': 0, 'weak_extractions': 0}, 'note': 'ID keys are inferred from common field names; hashes are not recomputed across semantic stages.'}

## Source and parser probes
- OpenAlex: measured (200)
- Crossref: measured (200)
- Unpaywall: blocked (email_parameter_required; no secret supplied)
- Europe PMC: measured (200)
- PyMuPDF: measured
- ChromaDB: measured
- Optional structural parsers: {'PyMuPDF': {'available': True}, 'ChromaDB': {'available': True}, 'requests': {'available': True}, 'psutil': {'available': False}, 'GROBID': {'available': False}, 'Docling': {'available': False}, 'MinerU': {'available': False}}

## Cells A-E

| Cell | Status |
|---|---|
| A | PENDING |
| B | PENDING |
| C | PENDING |
| D | PENDING |
| E | PENDING |

## Limitations
- A-E retrieval, reranking, structured extraction, stress, and abstention cells remain PENDING.
- Structural section/table/figure proxies remain PENDING; text extraction alone is not structural validation.
- Unpaywall was not called because its public endpoint requires a contact email; no credential or secret was supplied.
- The decision is NOT READY until the required cells and structural/parser evidence are measured.
