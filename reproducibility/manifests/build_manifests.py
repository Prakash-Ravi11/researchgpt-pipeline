"""Build corpus manifests: POINTERS + hashes, never content.

Emits one manifest per corpus (canonical 60 / data_test 8 / medical 50). Per paper:
identifiers (DOI / arXiv / PMCID), SHA-256 of the retrieved file if we hold one,
acquisition status, representation type, and which source accepted it.

Ships no PDF and no abstract text. A reproducer fetches and verifies against the
sha256 field rather than receiving the file.

  python reproducibility/manifests/build_manifests.py

REFUSES TO RUN when any source is missing (exit 2, nothing written). Most sources
are gitignored, so on a clean checkout this script cannot rebuild anything -- and
a partial rebuild would silently overwrite the shipped manifests with a degraded
set. Run it only on a machine holding the full run tree.
"""
from __future__ import annotations
import hashlib, json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent

# Each entry is (metadata json, label). The corpora are manifested AS THE
# EXPERIMENTS USED THEM, which for medical means two distinct frozen states -- not
# the live data/ copy, which has since drifted (see medical50_LIVE_DRIFT below).
CORPORA = {
    "canonical60": ROOT / "experiments/document_evidence_pipeline/runs/prodab-20260902T004416Z/canonical/raw_metadata/collected_papers.json",
    "data_test8":  ROOT / "data_test/raw_metadata/collected_papers.json",
    # 19 full-text; the state MEDICAL_RECHUNK + MEDICAL_SELECTOR_CONTROL measured (Table 5b)
    "medical50_frozen": Path(__file__).resolve().parent / "sources/medical50_frozen_collected_papers.json",
    # 23 full-text / 11 JATS; the state BINDING_VALIDATION measured (Table 5a)
    "medical50_reacquired": ROOT / "experiments/document_evidence_pipeline/runs/medical_reacquire/raw_metadata/collected_papers.json",
}
# Where the committed experiments' retrieved files actually live, per corpus.
RUN_DIRS = {
    "canonical60": ["experiments/document_evidence_pipeline/runs/prodab-20260902T004416Z/canonical/pdfs"],
    "data_test8":  ["data_test/pdfs",
                    "experiments/document_evidence_pipeline/runs/secondcorpus-datatest/pdfs"],
    "medical50_frozen": ["data/pdfs"],
    "medical50_reacquired": ["experiments/document_evidence_pipeline/runs/medical_reacquire/pdfs"],
}


def sha256(p: Path) -> str | None:
    try:
        h = hashlib.sha256()
        with p.open("rb") as f:
            for blk in iter(lambda: f.read(1 << 20), b""):
                h.update(blk)
        return h.hexdigest()
    except OSError:
        return None


def find_file(pid: str, dirs: list[str]) -> Path | None:
    for d in dirs:
        for ext in (".pdf", ".xml"):
            p = ROOT / d / f"{pid}{ext}"
            if p.exists():
                return p
    return None


def preflight() -> list[str]:
    """Every reason this run would produce a degraded manifest. Empty list = safe.

    Three of the four metadata sources and three of the five retrieved-file
    directories are gitignored, so in a clean checkout they are simply absent.
    This script used to SKIP them, exit 0, and write the survivors -- which
    silently replaced the shipped manifests with a one-corpus index.json and a
    medical50_frozen.json reporting n_files_hashed 0. Refusing is the only safe
    behaviour: a partial rebuild is indistinguishable from a real result.
    """
    problems = []
    for name, meta in CORPORA.items():
        if not meta.exists():
            problems.append(f"{name}: metadata source absent -- {meta}")
        dirs = [d for d in RUN_DIRS[name] if (ROOT / d).is_dir()]
        if not dirs:
            problems.append(f"{name}: no retrieved-file directory present -- "
                            f"none of {RUN_DIRS[name]} exists under {ROOT}")
    return problems


def main() -> int:
    problems = preflight()
    if problems:
        print("REFUSING TO RUN -- sources missing. Nothing was written.\n")
        for p in problems:
            print(f"  MISSING  {p}")
        print("\nThe corpus metadata and the retrieved PDFs live outside the repository:")
        print("  experiments/document_evidence_pipeline/runs/  is gitignored (528 MB)")
        print("  data/pdfs/  data_test/  are gitignored")
        print("Rebuild only on a machine holding the full run tree. On a clean checkout the")
        print("shipped manifests in reproducibility/manifests/ ARE the artifact -- read-only.")
        print("If a previous run already overwrote them:  git checkout -- reproducibility/manifests/")
        return 2

    index = {}
    for name, base in CORPORA.items():
        meta = base
        papers = json.loads(meta.read_text(encoding="utf-8"))
        rows, hashed, missing = [], 0, 0
        for p in papers:
            pid = p.get("paperId") or p.get("paper_id")
            ext = p.get("externalIds") or {}
            f = find_file(pid, RUN_DIRS[name])
            digest = sha256(f) if f else None
            if digest: hashed += 1
            elif p.get("has_full_text"): missing += 1
            rows.append({
                "paper_id": pid,
                "doi": ext.get("DOI"), "arxiv": ext.get("ArXiv"), "pmcid": ext.get("PubMedCentral"),
                "acquisition_status": p.get("acquisition_status")
                    or ("FULL_TEXT" if p.get("has_full_text") else "NO_ACCESSIBLE_FULL_TEXT"),
                "representation_type": p.get("representation_type")
                    or ("pdf" if p.get("has_full_text") else "abstract"),
                "accepted_source": p.get("pdf_source"),
                "retrieved_file": (str(f.relative_to(ROOT)).replace("\\", "/") if f else None),
                "sha256": digest,
            })
        man = {
            "corpus": name,
            "n_papers": len(rows),
            "n_full_text": sum(1 for r in rows if r["acquisition_status"] == "FULL_TEXT"),
            "n_files_hashed": hashed,
            "n_full_text_without_local_file": missing,
            "identifier_coverage": {
                "doi": sum(1 for r in rows if r["doi"]),
                "arxiv": sum(1 for r in rows if r["arxiv"]),
                "pmcid": sum(1 for r in rows if r["pmcid"]),
            },
            "representation": _count(rows, "representation_type"),
            "accepted_source": _count(rows, "accepted_source"),
            "retrieved_file_locations": RUN_DIRS[name],
            "note_tldr": ("Collected with `tldr` in semantic_scholar.FIELDS. That field was "
                          "dropped post-freeze; nothing in src/ consumes it, so no result "
                          "changes, but a fresh collection will lack it. Not a discrepancy."),
            "papers": rows,
        }
        (OUT / f"{name}.json").write_text(json.dumps(man, indent=2), encoding="utf-8")
        index[name] = {k: man[k] for k in
                       ("n_papers", "n_full_text", "n_files_hashed",
                        "n_full_text_without_local_file", "identifier_coverage",
                        "representation", "accepted_source")}
        print(f"  {name:12} {len(rows):3} papers | {man['n_full_text']:3} full-text | "
              f"{hashed:3} files hashed | {missing} full-text w/o local file")
    (OUT / "index.json").write_text(json.dumps(index, indent=2), encoding="utf-8")
    return 0


def _count(rows, key):
    out = {}
    for r in rows:
        out[str(r.get(key))] = out.get(str(r.get(key)), 0) + 1
    return dict(sorted(out.items(), key=lambda kv: -kv[1]))


if __name__ == "__main__":
    raise SystemExit(main())
