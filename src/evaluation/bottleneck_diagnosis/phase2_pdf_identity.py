"""Phase 2 -- identify and verify the physical PDFs behind the candidate dataset, read-only.

    PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe src/evaluation/bottleneck_diagnosis/phase2_pdf_identity.py

Opened read-only: the candidate ZIP, the medical30 acquisition record (ACQ), repository manifests,
and the PDFs. Nothing is moved, renamed, copied or modified. The only files written are the two
outputs next to this script:
  pdf_identity_manifest.csv   one row per candidate paper
  pdf_identity_details.json   search scope, every hit, per-copy hashes, per-check evidence

Identity key: `source_filename` in each paper JSON (the candidate README: "identified by
source_filename"). The candidate JSONs record no hash; SHA-256 identity is therefore established
against the acquisition record and across copies.

Search
  S1 (names only, no file content read) every file under NAME_ROOTS whose name contains the
     paper's S2 id (source_filename stem), its arXiv id, or a non-arXiv DOI suffix (>= 8 chars).
     Matched PDFs are then hashed.
  S2 (content, only inside this repository's git worktrees = project data) SHA-256 of every
     PDF, which finds renamed byte-identical copies, and the page-1 text of every PDF checked
     for each normalized candidate title, which finds other versions.

Pre-registered decision rule. It was fixed before any result was seen and must not be tuned
afterwards.
  Identity checks:
    T1  an exact-name copy exists
    T2  all exact-name copies are byte-identical (SHA-256)
    T3  SHA-256 equals the ACQ document_sha256 for the same S2 paperId
    T4  PDF page count equals candidate 01_metadata.pages
    T5  the normalized candidate title is a substring of the normalized text of PDF pages 1-2
        (T5p fallback: >= T5P_MIN of title words with 3+ chars appear in pages 1-2)
    T6  >= T6_MIN of candidate author surnames appear in pages 1-2 (n/a if not reported)
    T7  the candidate arXiv base id appears in the PDF text (n/a if not reported)
    T8  01_metadata.evidence.source_text is found on its stated page
    T9  >= T9_MIN of checkable non-claim evidence snippets (sections 02-09, 11, 13;
        normalized length >= MIN_SNIPPET) are found anywhere in the PDF
  Status, evaluated in this order:
    MISSING                 not T1
    AMBIGUOUS               T1 and not T2
    MISMATCH                not (T5 or T5p) and T9 rate < MISMATCH_T9_MAX
    MATCH_VERIFIED          T1-T5 (exact), T8 and T9 all pass, and T6/T7 pass or are n/a
    MATCH_WITH_DISCREPANCY  anything else; the failed checks are listed
  Other PDFs that appear to be the same paper but are not exact-name copies are reported in
  `other_related_pdfs`. They do not change the status, because the identity key is the filename.
  Candidate-consistency checks. These are reported but never change the identity status:
    C1  every candidate page reference lies within 1..page_count
    C2  every table bbox lies inside its PDF page rectangle (BBOX_TOL pt tolerance)
    C3  the snippet is found on its stated page (as opposed to elsewhere)
    C4  candidate vs acquisition record: title similarity, year, arXiv id
  verification_method is the weakest method the status relies on (normalized text matching);
  verification_confidence is high / medium / low per the rule in `decide`.
"""
from __future__ import annotations

import csv
import difflib
import hashlib
import json
import os
import platform
import re
import subprocess
import sys
import unicodedata
import zipfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import pymupdf

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
ZIP = ROOT / "src" / "evaluation" / "candidate_gold" / "researchgpt_candidate_gold_30_2026-09-28 (1).zip"
ACQ = Path(r"C:\Users\Praka\Downloads\rgpt-exp-parser\data\medical30_eval\raw_metadata\collected_papers.json")
ACQ_ROOT = ACQ.parents[3]
NAME_ROOTS = [Path.home() / d for d in ("Downloads", "Documents", "OneDrive", "Desktop")]
SKIP_DIRS = {".git", ".venv", "venv", "node_modules", "__pycache__", "chroma_db", "chroma_users",
             "site-packages", ".cache"}
OUT_CSV = HERE / "pdf_identity_manifest.csv"
OUT_JSON = HERE / "pdf_identity_details.json"
NONCLAIM_SECTIONS = ["02_research_problem", "03_research_objective", "04_methodology", "05_dataset",
                     "06_preprocessing", "07_experimental_setup", "08_baselines_and_comparisons",
                     "09_evaluation_metrics", "11_qualitative_results", "13_limitations"]
ALL_SECTIONS = NONCLAIM_SECTIONS + ["10_quantitative_results", "12_claims_and_conclusions"]
MIN_SNIPPET, T5P_MIN, T6_MIN, T9_MIN, MISMATCH_T9_MAX, BBOX_TOL = 20, 0.9, 0.5, 0.8, 0.5, 1.0
ARXIV_RE = re.compile(r"\d{4}\.\d{4,5}")


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def norm(s: str) -> str:
    """NFKD (splits ligatures and accents), casefold, keep [0-9a-z] only."""
    return re.sub(r"[^0-9a-z]+", "", unicodedata.normalize("NFKD", s or "").casefold())


def words(s: str, n: int = 3) -> set[str]:
    return set(re.findall(rf"[0-9a-z]{{{n},}}", unicodedata.normalize("NFKD", s or "").casefold()))


def locate(sn: str, pages: list[str], doc: str, stated: int) -> tuple[str, int | None]:
    """Where a normalized snippet occurs: stated | adjacent | elsewhere | prefix_only | not_found."""
    n = len(pages)
    if 1 <= stated <= n:
        if sn in pages[stated - 1] or (stated < n and sn in pages[stated - 1] + pages[stated]):
            return "stated", stated
        for q in (stated - 1, stated + 1):
            if 1 <= q <= n and sn in pages[q - 1]:
                return "adjacent", q
    for q in range(1, n + 1):
        if sn in pages[q - 1]:
            return "elsewhere", q
    if sn in doc:
        return "elsewhere", None
    return ("prefix_only", None) if sn[:40] in doc else ("not_found", None)


def git(*args: str) -> str:
    try:
        return subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, text=True, check=True).stdout.strip()
    except Exception as e:  # recorded, not fatal
        return f"UNAVAILABLE: {e}"


def walk_files(root: Path):
    for dp, dns, fns in os.walk(root):
        dns[:] = [d for d in dns if d not in SKIP_DIRS]
        for fn in fns:
            yield Path(dp) / fn


def surnames(authors: str) -> list[str]:
    if not authors or authors == "NOT_REPORTED":
        return []
    parts = authors.split(";") if ";" in authors else authors.split(",")
    return [p.strip().split()[-1] for p in parts if p.strip()]


def as_obj(v):
    return json.loads(v) if isinstance(v, str) and v[:1] in "[{" else v


def add_related(bucket: dict, path: str, **info) -> None:
    key = os.path.normcase(path)
    if key in bucket:
        bucket[key]["basis"] += ";" + info["basis"]
    else:
        bucket[key] = {"path": path, **info}


def _selfcheck() -> None:
    assert norm("Weakly-\nsupervised ﬁne") == "weaklysupervisedfine"
    assert words("Alenyá, U-Net") >= {"alenya", "net"}
    pages = [norm("title page"), norm("alpha beta gamma delta"), norm("epsilon")]
    doc = "".join(pages)
    assert locate(norm("beta gamma"), pages, doc, 2) == ("stated", 2)
    assert locate(norm("beta gamma"), pages, doc, 3) == ("adjacent", 2)
    assert locate(norm("delta epsilon"), pages, doc, 2) == ("stated", 2)          # spans a page break
    assert locate(norm("title page"), pages, doc, 3) == ("elsewhere", 1)
    assert locate(norm("zeta"), pages, doc, 1) == ("not_found", None)
    assert surnames("Jia Fu; Tao Lu") == ["Fu", "Lu"] and surnames("NOT_REPORTED") == []


def decide(t: dict) -> tuple[str, str, list[str]]:
    """Apply the pre-registered rule. t maps check -> True / False / None (n/a)."""
    failed = [k for k in ("T1", "T2", "T3", "T4", "T5", "T6", "T7", "T8", "T9") if t.get(k) is False]
    if not t["T1"]:
        return "MISSING", "high", failed
    if not t["T2"]:
        return "AMBIGUOUS", "high", failed
    if not (t["T5"] or t["T5p"]) and t["T9_rate"] < MISMATCH_T9_MAX:
        return "MISMATCH", "medium", failed
    if not failed:
        return "MATCH_VERIFIED", "high", failed
    strong = t["T3"] and (t["T5"] or t["T5p"]) and t["T9"]
    return "MATCH_WITH_DISCREPANCY", ("medium" if strong else "low"), failed


def main() -> None:
    _selfcheck()
    pymupdf.TOOLS.mupdf_display_errors(False)
    zip_sha_before = sha256_file(ZIP)
    zf = zipfile.ZipFile(ZIP)
    papers = [json.loads(zf.read(n)) for n in sorted(zf.namelist()) if re.fullmatch(r"P\d{3}\.json", n)]
    acq = {r["paperId"]: r for r in json.loads(ACQ.read_text(encoding="utf-8"))}

    # other manifests in this repository that record a sha256 per paper
    manifest_sha: dict[str, list] = {}

    def walk_manifest(x, name):
        if isinstance(x, dict):
            pid = x.get("paper_id") or x.get("paperId")
            if pid and x.get("sha256"):
                manifest_sha.setdefault(pid, []).append({"manifest": name, "sha256": x["sha256"]})
            for v in x.values():
                walk_manifest(v, name)
        elif isinstance(x, list):
            for v in x:
                walk_manifest(v, name)
    for mf in sorted((ROOT / "reproducibility" / "manifests").glob("*.json")):
        walk_manifest(json.loads(mf.read_text(encoding="utf-8")), mf.name)

    # name tokens per paper
    tokens = {}
    for d in papers:
        stem = d["source_filename"][:-4].lower()
        ext = as_obj(acq.get(stem, {}).get("externalIds")) or {}
        toks = {stem: "s2_id_in_name"}
        for src in (d["01_metadata"]["arxiv_id"], ext.get("ArXiv")):
            m = ARXIV_RE.search(src or "")
            if m:
                toks[m.group(0)] = "arxiv_id_in_name"
        doi = ext.get("DOI") or ""
        suffix = doi.rsplit("/", 1)[-1].lower()
        if doi and "arxiv" not in doi.lower() and len(suffix) >= 8:
            toks[suffix] = "doi_suffix_in_name"
        tokens[d["paper_id"]] = toks

    # S1: name search (no content read)
    s1_hits = {d["paper_id"]: [] for d in papers}
    n_s1 = 0
    roots_s1 = [r for r in NAME_ROOTS if r.is_dir()]
    for root in roots_s1:
        for p in walk_files(root):
            n_s1 += 1
            low = p.name.lower()
            for pid, toks in tokens.items():
                for tok, kind in toks.items():
                    if tok in low:
                        s1_hits[pid].append({"path": str(p), "basis": kind, "token": tok})

    # exact-name copies, hashes, canonical path
    per = {}
    for d in papers:
        pid, fname = d["paper_id"], d["source_filename"]
        exact = sorted({h["path"] for h in s1_hits[pid] if Path(h["path"]).name.lower() == fname.lower()})
        copies = [{"path": p, "sha256": sha256_file(Path(p)), "size_bytes": Path(p).stat().st_size} for p in exact]
        r = acq.get(fname[:-4].lower())
        acq_path = str((ACQ_ROOT / r["pdf_path"]).resolve()) if r and r.get("pdf_path") else None
        canon = next((c for c in copies if acq_path and os.path.normcase(c["path"]) == os.path.normcase(acq_path)),
                     next((c for c in copies if "medical30_eval" in c["path"] and "_staging" not in c["path"]),
                          copies[0] if copies else None))
        per[pid] = {"copies": copies, "canonical": canon, "acq": r, "acq_path": acq_path}
    canon_hash = {v["canonical"]["sha256"]: pid for pid, v in per.items() if v["canonical"]}
    exact_paths = {os.path.normcase(c["path"]) for v in per.values() for c in v["copies"]}
    title_norm = {d["paper_id"]: norm(d["01_metadata"]["title"]) for d in papers}

    # S2: content search inside this repository's worktrees
    worktrees = [Path(l[len("worktree "):]) for l in git("worktree", "list", "--porcelain").splitlines()
                 if l.startswith("worktree ")] or [ROOT]
    related: dict[str, dict] = {d["paper_id"]: {} for d in papers}
    n_pdf, unreadable = 0, []
    for wt in worktrees:
        for p in walk_files(wt):
            if p.suffix.lower() != ".pdf" or os.path.normcase(str(p)) in exact_paths:
                continue
            n_pdf += 1
            h = sha256_file(p)
            if h in canon_hash:
                add_related(related[canon_hash[h]], str(p), basis="sha256_identical_to_canonical",
                            sha256=h, is_pdf=True, identical_to_canonical=True)
                continue
            try:
                with pymupdf.open(p) as doc:
                    first = norm(doc[0].get_text()) if doc.page_count else ""
            except Exception as e:
                unreadable.append({"path": str(p), "error": str(e)[:200]})
                continue
            for pid, tn in title_norm.items():
                if len(tn) >= MIN_SNIPPET and tn in first:
                    add_related(related[pid], str(p), basis="candidate_title_on_page_1",
                                sha256=h, is_pdf=True, identical_to_canonical=False)
    for pid, hits in s1_hits.items():
        c = per[pid]["canonical"]
        for hit in hits:
            key = os.path.normcase(hit["path"])
            if key in exact_paths:
                continue
            if key in related[pid]:
                related[pid][key]["basis"] += ";" + hit["basis"]
                continue
            p = Path(hit["path"])
            is_pdf = p.suffix.lower() == ".pdf"
            try:
                h = sha256_file(p) if is_pdf else None
            except OSError as e:
                h = f"UNREADABLE: {e}"
            add_related(related[pid], hit["path"], basis=hit["basis"], token=hit["token"], sha256=h,
                        is_pdf=is_pdf, identical_to_canonical=bool(c and h == c["sha256"]))

    rows, details = [], []
    for d in papers:
        pid, fname, meta = d["paper_id"], d["source_filename"], d["01_metadata"]
        v = per[pid]
        c, r = v["canonical"], v["acq"]
        ext = as_obj((r or {}).get("externalIds")) or {}
        rel = list(related[pid].values())
        idents = [x for x in rel if x["identical_to_canonical"]]
        others = [x for x in rel if x["is_pdf"] and not x["identical_to_canonical"]]
        non_pdf = [x for x in rel if not x["is_pdf"]]
        t = {"T1": c is not None}
        t["T2"] = len({x["sha256"] for x in v["copies"]}) == 1 if c else None
        t["T3"] = bool(c and r and r.get("document_sha256") == c["sha256"])
        oms = manifest_sha.get(fname[:-4], [])
        row = {"paper_id": pid, "json_filename": f"{pid}.json", "pdf_filename": fname, "s2_paper_id": fname[:-4],
               "pdf_exists": c is not None, "canonical_pdf_path": c["path"] if c else "",
               "exact_name_copies": len(v["copies"]),
               "exact_name_copy_paths": ";".join(x["path"] for x in v["copies"]),
               "copies_byte_identical": t["T2"], "sha256": c["sha256"] if c else "",
               "size_bytes": c["size_bytes"] if c else "", "acquisition_record": bool(r),
               "acquisition_sha256_match": t["T3"],
               "acquisition_pdf_path_is_canonical": bool(c and v["acq_path"] and
                                                         os.path.normcase(v["acq_path"]) == os.path.normcase(c["path"])),
               "other_manifest_sha256_match": ";".join(f'{m["manifest"]}={m["sha256"] == (c or {}).get("sha256")}'
                                                       for m in oms) or "none",
               "identical_copies_elsewhere": len(idents), "other_related_pdfs": len(others),
               "other_related_pdfs_basis": ";".join(sorted({b for x in others for b in x["basis"].split(";")})),
               "non_pdf_name_hits": len(non_pdf)}
        det = {"paper_id": pid, "source_filename": fname, "copies": v["copies"], "related_files": rel,
               "acquisition_pdf_path": v["acq_path"],
               "acquisition_identity_validation": (r or {}).get("identity_validation"),
               "acquisition_content_validation": (r or {}).get("content_validation"),
               "other_manifest_sha256": oms}
        if not c:
            t.update(T4=None, T5=None, T5p=None, T6=None, T7=None, T8=None, T9=None, T9_rate=0.0)
            status, conf, failed = decide(t)
            row.update(identity_status=status, checks_failed=";".join(failed),
                       verification_method="exact", verification_confidence=conf)
            rows.append(row)
            details.append({**det, "checks": t})
            continue

        pymupdf.TOOLS.reset_mupdf_warnings()
        with pymupdf.open(c["path"]) as doc:
            n = doc.page_count
            raw_pages = [pg.get_text() for pg in doc]
            rects = [(pg.rect, pg.rotation) for pg in doc]
            md = doc.metadata or {}
            encrypted = doc.is_encrypted
        warnings = [w for w in pymupdf.TOOLS.mupdf_warnings().splitlines() if w.strip()]
        pages = [norm(x) for x in raw_pages]
        docn = "".join(pages)
        head = raw_pages[0] + "\n" + (raw_pages[1] if n > 1 else "")
        headn = norm(head)
        raw_all = "\n".join(raw_pages)

        t["T4"] = n == meta["pages"]
        t["T5"] = bool(title_norm[pid]) and title_norm[pid] in headn
        tw = words(meta["title"])
        cov = len(tw & words(head)) / len(tw) if tw else 0.0
        t["T5p"] = cov >= T5P_MIN
        sn = surnames(meta["authors"])
        head_tokens = words(head, 2)
        found_sn = []
        for s in sn:
            toks = re.findall(r"[a-z]+", unicodedata.normalize("NFKD", s).casefold())
            if toks and all(tok in head_tokens for tok in toks):
                found_sn.append(s)
        t["T6"] = (len(found_sn) / len(sn) >= T6_MIN) if sn else None
        cand_arxiv = ARXIV_RE.search(meta["arxiv_id"] or "")
        arxiv_versions = (sorted(set(re.findall(re.escape(cand_arxiv.group(0)) + r"(v\d+)?", raw_all)))
                          if cand_arxiv else [])
        t["T7"] = bool(re.search(re.escape(cand_arxiv.group(0)), raw_all)) if cand_arxiv else None
        me = meta["evidence"]
        me_loc = locate(norm(me["source_text"]), pages, docn, me["page"])
        t["T8"] = me_loc[0] == "stated"

        snippets = []
        for s in NONCLAIM_SECTIONS:
            for e in d[s]["evidence"]:
                snn = norm(e["source_text"])
                if len(snn) < MIN_SNIPPET:
                    snippets.append({"section": s, "page": e["page"], "result": "too_short", "found_page": None})
                    continue
                res, fp = locate(snn, pages, docn, e["page"])
                snippets.append({"section": s, "page": e["page"], "result": res, "found_page": fp,
                                 "text_head": e["source_text"][:60]})
        chk = [x for x in snippets if x["result"] != "too_short"]
        found = [x for x in chk if x["result"] in ("stated", "adjacent", "elsewhere")]
        t["T9_rate"] = len(found) / len(chk) if chk else 0.0
        t["T9"] = t["T9_rate"] >= T9_MIN if chk else False

        # candidate-consistency checks (never change identity status)
        refs = [("01_metadata.evidence", me["page"])] + [(s, e["page"]) for s in ALL_SECTIONS for e in d[s]["evidence"]]
        tg, ctl = d["TABLE_GROUND_TRUTH"], d["CLAIM_TABLE_LINKING"]
        refs += [("table", x["page"]) for x in tg["tables"]] + [("table_inventory", x["page"]) for x in tg["table_inventory"]]
        refs += [("cell", x["page"]) for x in tg["cells"]] + [("cross_reference", x["page"]) for x in ctl["cross_references"]]
        refs += [("relationship", x["evidence_page"]) for x in ctl["claim_table_relationships"]]
        refs += [("numeric_case", x["page"]) for x in d["numeric_normalization_cases"]]
        out_of_range = [{"where": w, "page": p} for w, p in refs if not (isinstance(p, int) and 1 <= p <= n)]
        tables = []
        for tb in tg["tables"]:
            p, b = tb["page"], tb["bbox"]
            if 1 <= p <= n:
                rect, rot = rects[p - 1]
                inside = (b[0] >= rect.x0 - BBOX_TOL and b[1] >= rect.y0 - BBOX_TOL and
                          b[2] <= rect.x1 + BBOX_TOL and b[3] <= rect.y1 + BBOX_TOL)
                tables.append({"table_id": tb["table_id"], "printed_label": tb["printed_label"], "page": p, "bbox": b,
                               "page_rect": [rect.x0, rect.y0, rect.x1, rect.y1], "rotation": rot, "inside": inside})
            else:
                tables.append({"table_id": tb["table_id"], "printed_label": tb["printed_label"], "page": p,
                               "bbox": b, "inside": None})
        s2_title = (r or {}).get("title") or ""
        s2_arxiv = ext.get("ArXiv") or ""
        s2_doi = ext.get("DOI") or ""
        status, conf, failed = decide(t)
        ncop = len(v["copies"])
        evidence = [f"exact filename, {ncop} cop{'y' if ncop == 1 else 'ies'}"
                    f"{', byte-identical' if t['T2'] else ', DIFFERENT BYTES'}",
                    f"sha256 {'==' if t['T3'] else '!='} acquisition record",
                    f"pages {n} {'==' if t['T4'] else '!='} candidate {meta['pages']}",
                    f"title {'found' if t['T5'] else 'NOT found'} in pages 1-2 (word coverage {cov:.2f})",
                    f"authors {len(found_sn)}/{len(sn)}" if sn else "authors n/a",
                    (f"arXiv {cand_arxiv.group(0)} {'in' if t['T7'] else 'NOT in'} text" if cand_arxiv else "arXiv n/a"),
                    f"metadata evidence {me_loc[0]}",
                    f"non-claim snippets found {len(found)}/{len(chk)}"]
        row.update({
            "pdf_page_count": n, "candidate_pages_declared": meta["pages"], "page_count_match": t["T4"],
            "acquisition_pdf_pages": ((r or {}).get("content_validation") or {}).get("metrics", {}).get("pdf_pages"),
            "pdf_encrypted": encrypted, "mupdf_warnings": len(warnings), "pdf_producer": md.get("producer", ""),
            "candidate_title": meta["title"], "s2_title": s2_title, "pdf_metadata_title": md.get("title", ""),
            "title_in_pdf_pages_1_2": t["T5"], "title_word_coverage": round(cov, 3),
            "candidate_vs_s2_title_similarity": round(difflib.SequenceMatcher(None, title_norm[pid], norm(s2_title)).ratio(), 3),
            "author_surnames_found": f"{len(found_sn)}/{len(sn)}" if sn else "n/a",
            "candidate_arxiv_id": meta["arxiv_id"], "arxiv_in_pdf_text": t["T7"],
            "arxiv_versions_in_text": ";".join(x or "(no version)" for x in arxiv_versions),
            "s2_arxiv_id": s2_arxiv,
            "arxiv_candidate_equals_s2": (cand_arxiv.group(0) == s2_arxiv) if cand_arxiv and s2_arxiv else None,
            "candidate_year": meta["year"], "s2_year": (r or {}).get("year"),
            "year_match": str(meta["year"]) == str((r or {}).get("year")),
            "s2_doi": s2_doi, "s2_doi_in_pdf_text": (s2_doi.lower() in raw_all.lower()) if s2_doi else None,
            "metadata_evidence_location": me_loc[0],
            "evidence_snippets_checkable": len(chk), "evidence_found_anywhere": len(found),
            "evidence_found_on_stated_page": sum(x["result"] == "stated" for x in chk),
            "evidence_found_adjacent_page": sum(x["result"] == "adjacent" for x in chk),
            "evidence_found_elsewhere": sum(x["result"] == "elsewhere" for x in chk),
            "evidence_prefix_only": sum(x["result"] == "prefix_only" for x in chk),
            "evidence_not_found": sum(x["result"] == "not_found" for x in chk),
            "evidence_found_rate": round(t["T9_rate"], 3),
            "candidate_page_refs": len(refs), "candidate_page_refs_out_of_range": len(out_of_range),
            "table_pages_within_pdf": f"{sum(x['inside'] is not None for x in tables)}/{len(tables)}",
            "table_bbox_inside_page": f"{sum(bool(x['inside']) for x in tables)}/{len(tables)}",
            "identity_status": status, "identity_evidence": "; ".join(evidence),
            "checks_failed": ";".join(failed), "verification_method": "normalized",
            "verification_confidence": conf,
        })
        rows.append(row)
        details.append({**det, "checks": t, "title_word_coverage": cov, "authors_checked": sn,
                        "authors_found": found_sn, "metadata_evidence": {"page": me["page"], "result": me_loc},
                        "pdf_metadata": md, "mupdf_warnings": warnings[:20], "snippets": snippets,
                        "candidate_page_refs_out_of_range": out_of_range, "tables": tables})

    # hash stability: re-hash every copy after all reads
    for v in per.values():
        for x in v["copies"]:
            x["sha256_after"] = sha256_file(Path(x["path"]))
    stable = {pid: all(x["sha256"] == x["sha256_after"] for x in v["copies"]) for pid, v in per.items()}
    for row in rows:
        row["sha256_stable_during_run"] = stable[row["paper_id"]] if row["pdf_exists"] else ""
    zip_sha_after = sha256_file(ZIP)

    fields = list(dict.fromkeys(k for row in rows for k in row))
    with open(OUT_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    OUT_JSON.write_text(json.dumps({
        "artifact": "pdf_identity_details",
        "provenance": {"generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                       "script": str(Path(__file__).resolve().relative_to(ROOT)).replace("\\", "/"),
                       "git_head": git("rev-parse", "HEAD"), "git_branch": git("rev-parse", "--abbrev-ref", "HEAD"),
                       "python": sys.version.split()[0], "pymupdf": pymupdf.VersionBind, "platform": platform.platform(),
                       "zip_sha256_before": zip_sha_before, "zip_sha256_after": zip_sha_after,
                       "acquisition_record": str(ACQ), "acquisition_record_sha256": sha256_file(ACQ)},
        "decision_rule": __doc__,
        "thresholds": {"MIN_SNIPPET": MIN_SNIPPET, "T5P_MIN": T5P_MIN, "T6_MIN": T6_MIN, "T9_MIN": T9_MIN,
                       "MISMATCH_T9_MAX": MISMATCH_T9_MAX, "BBOX_TOL": BBOX_TOL},
        "search": {"S1_name_roots": [str(x) for x in roots_s1],
                   "S1_roots_absent": [str(x) for x in NAME_ROOTS if not x.is_dir()],
                   "S1_files_scanned": n_s1, "S2_worktrees": [str(x) for x in worktrees],
                   "S2_other_pdfs_scanned": n_pdf, "S2_unreadable": unreadable,
                   "skipped_dir_names": sorted(SKIP_DIRS), "name_tokens": tokens},
        "papers": details}, indent=1, ensure_ascii=False, default=str), encoding="utf-8")

    print(f"wrote {OUT_CSV.relative_to(ROOT)} and {OUT_JSON.relative_to(ROOT)}")
    print(f"S1 files scanned {n_s1} | S2 other PDFs scanned {n_pdf} | unreadable {len(unreadable)}")
    print(f"zip sha256 unchanged: {zip_sha_before == zip_sha_after} | all copies hash-stable: {all(stable.values())}")
    print("status:", dict(Counter(r["identity_status"] for r in rows)))
    for r in rows:
        print(f"{r['paper_id']} {r['identity_status']:<23} {r.get('verification_confidence', ''):<6} "
              f"pages {r.get('pdf_page_count', '')}/{r.get('candidate_pages_declared', '')} "
              f"T5={r.get('title_in_pdf_pages_1_2')} cov={r.get('title_word_coverage')} "
              f"au={r.get('author_surnames_found')} ev={r.get('evidence_found_anywhere')}/{r.get('evidence_snippets_checkable')} "
              f"stated={r.get('evidence_found_on_stated_page')} me={r.get('metadata_evidence_location')} "
              f"bbox={r.get('table_bbox_inside_page')} rel={r.get('other_related_pdfs')} failed=[{r.get('checks_failed')}]")


if __name__ == "__main__":
    main()
