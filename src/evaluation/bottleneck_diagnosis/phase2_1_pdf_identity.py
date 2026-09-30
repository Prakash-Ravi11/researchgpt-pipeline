"""Phase 2.1 -- corrected PDF identity evaluator (evaluator-only fix of T5, T6, T7).

    PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe src/evaluation/bottleneck_diagnosis/phase2_1_pdf_identity.py

Phase 2.1 corrects three defects in the Phase 2 evaluator (phase2_pdf_identity.py, imported here as `v1`).
Every other check, threshold and helper is taken unchanged from `v1`. The run refuses to write output
unless the unchanged checks reproduce the Phase 2 values exactly. Phase 2 outputs are read, never written.

Inputs (read-only): the Phase 2 manifest and details (the PDF set and hashes to verify against), the
candidate ZIP, the acquisition record, and the PDFs. Outputs (new files next to this script):
  pdf_identity_manifest_v2.csv   pdf_identity_details_v2.json   phase2_1_pdf_identity_report.md

Pre-run gate: every PDF copy recorded in Phase 2 must exist and hash to its Phase 2 SHA-256, otherwise
the run stops. PDFs are never substituted, downloaded, or searched for again.

Corrected rules (the Phase 2 rule text is preserved in pdf_identity_details.json):
  T5  A candidate title of NOT_REPORTED (or empty) gives N/A. Otherwise the rule is unchanged: the
      normalized title must be a substring of normalized PDF pages 1-2 (T5p: >= 0.9 of title words present).
  T6  Each candidate surname (`surnames()` is unchanged: the last token of each ';'-separated name) is
      searched in the PyMuPDF span stream of pages 1-2, line by line, as a whole word only:
        match_exact               identical text (NFC), word boundary on both sides
        match_normalized          equal only after, as the first sufficient stage: case folding |
                                  compatibility decomposition (ligatures, e.g. U+FB00 'ff') | diacritic
                                  folding | removal of LaTeX spacing-accent glyphs (U+00B4 U+0060 U+00A8
                                  U+02D8 U+00B8 ...) and unification of dash/apostrophe variants
        match_trailing_marker     the surname is followed, with no space, by characters the PDF itself
                                  marks as an affiliation superscript: a span with the MuPDF superscript
                                  flag (flags & 1); a span <= 0.85x the line's largest font size whose
                                  baseline is raised >= 0.1x that size; or Unicode superscript characters
        ambiguous_unconfirmed_marker  followed by glued digits or single letters the PDF does NOT mark
                                  as superscript (e.g. plain 'Smith1'); not a match
        mismatch_candidate_includes_marker  the candidate surname only matches by absorbing a PDF
                                  superscript marker (e.g. candidate 'Agarwala' vs PDF 'Agarwal' + sup 'a')
        mismatch_not_found        no whole-word occurrence; a substring inside another word never counts
      Only the three match_* classes count as found. T6 = found/total >= T6_MIN (0.5, unchanged). N/A
      when the candidate reports no authors. The nearest PDF word (by edit distance) is recorded for
      non-matches for audit only; it never influences a decision.
  T7  The candidate arXiv id counts only if it equals the arXiv stamp on PAGE 1
      ('arXiv:<id>[vN] [<category>]'). When the candidate states a version, that must agree too. Ids
      found elsewhere (references, body, non-stamp mentions on page 1) are recorded for audit and never
      pass. N/A when the candidate reports no arXiv id.
  decide  Unchanged, except that an N/A title is neutral in the confidence clause instead of counting
      as a title failure. With an N/A title, MISMATCH is decided by the content check (T9) alone.
"""
from __future__ import annotations

import csv
import difflib
import json
import platform
import re
import sys
import unicodedata
import zipfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import pymupdf

import phase2_pdf_identity as v1

HERE = Path(__file__).resolve().parent
V1_CSV, V1_JSON = HERE / "pdf_identity_manifest.csv", HERE / "pdf_identity_details.json"
OUT_CSV, OUT_JSON = HERE / "pdf_identity_manifest_v2.csv", HERE / "pdf_identity_details_v2.json"
OUT_MD = HERE / "phase2_1_pdf_identity_report.md"
NA_VALUES = {"NOT_REPORTED", ""}
SPACING_ACCENTS = set("´`ˆ˜¨˘ˇ˙¸˛˚¯")
PUNCT_VARIANTS = str.maketrans({**dict.fromkeys("‐‑‒–—−", "-"),
                                **dict.fromkeys("‘’ʼ", "'")})
MARKER_SIZE_RATIO, MARKER_RAISE = 0.85, 0.1
STAMP_RE = re.compile(r"arXiv:\s*(\d{4}\.\d{4,5})(v\d+)?\s*\[\s*[A-Za-z][A-Za-z-]*(?:\.[A-Za-z-]+)?\s*\]")
MENTION_RE = re.compile(r"(?:arXiv\s*:?\s*(?:preprint\s*)?(?:arXiv\s*:?\s*)?|arxiv\.org/(?:abs|pdf)/|"
                        r"10\.48550/arXiv\.)(\d{4}\.\d{4,5})(v\d+)?", re.I)
MATCHED = ("match_exact", "match_normalized", "match_trailing_marker")
RANK = {c: i for i, c in enumerate(["mismatch_not_found", "mismatch_candidate_includes_marker",
                                    "ambiguous_unconfirmed_marker", "match_trailing_marker",
                                    "match_normalized", "match_exact"])}
UNCHANGED_FIELDS = ["sha256", "copies_byte_identical", "acquisition_sha256_match", "pdf_page_count",
                    "page_count_match", "metadata_evidence_location", "evidence_snippets_checkable",
                    "evidence_found_anywhere", "evidence_found_on_stated_page", "candidate_page_refs",
                    "candidate_page_refs_out_of_range", "table_pages_within_pdf", "table_bbox_inside_page"]


# --- T5 --------------------------------------------------------------------------------------
def t5_title_check(title: str, head_text: str) -> dict:
    if (title or "").strip() in NA_VALUES:
        return {"T5": None, "T5p": None, "coverage": None, "outcome": "na_title_not_reported"}
    tn = v1.norm(title)
    t5 = bool(tn) and tn in v1.norm(head_text)
    tw = v1.words(title)
    cov = len(tw & v1.words(head_text)) / len(tw) if tw else 0.0
    return {"T5": t5, "T5p": cov >= v1.T5P_MIN, "coverage": cov, "outcome": "found" if t5 else "not_found"}


# --- T6 --------------------------------------------------------------------------------------
def fold(s: str) -> str:
    """Comparison form: drop LaTeX spacing-accent glyphs, unify dash/apostrophe variants, NFKD,
    drop combining marks, casefold."""
    s = "".join(c for c in s if c not in SPACING_ACCENTS).translate(PUNCT_VARIANTS)
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c)).casefold()


def _strip_marks(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c)).casefold()


_STAGES = [("exact", lambda s: unicodedata.normalize("NFC", s)),
           ("case_folded", lambda s: unicodedata.normalize("NFC", s).lower()),   # lower(), not casefold():
           # casefold() already expands ligatures (U+FB00 -> 'ff'), which belongs to the next stage
           ("compatibility_decomposed", lambda s: unicodedata.normalize("NFKD", s).casefold()),
           ("diacritics_folded", _strip_marks),
           ("pdf_spacing_accents_and_punctuation", fold)]


def normalization_stage(candidate: str, pdf_raw: str) -> str | None:
    """The first normalization stage at which candidate and PDF text agree."""
    for name, f in _STAGES:
        if f(candidate) == f(pdf_raw):
            return name
    return None


def span_chars(spans: list[dict]) -> list[tuple[str, str | None]]:
    """(char, marker_evidence) for one PyMuPDF 'dict' line; marker_evidence None = body text."""
    spans = [s for s in spans if s.get("text")]
    if not spans:
        return []
    base = max(spans, key=lambda s: s["size"])
    out = []
    for s in spans:
        if s["flags"] & 1:
            ev = "mupdf_superscript_flag"
        elif (s["size"] <= MARKER_SIZE_RATIO * base["size"]
              and s["origin"][1] <= base["origin"][1] - MARKER_RAISE * base["size"]):
            ev = "smaller_raised_span"
        else:
            ev = None
        for ch in s["text"]:
            out.append((ch, ev or ("unicode_superscript" if unicodedata.decomposition(ch).startswith("<super>") else None)))
    return out


def pdf_lines(doc, pages: int = 2) -> list[tuple[int, list]]:
    out = []
    for pno in range(min(pages, doc.page_count)):
        for b in doc[pno].get_text("dict")["blocks"]:
            for ln in b.get("lines", []):
                chars = span_chars(ln["spans"])
                if chars:
                    out.append((pno + 1, chars))
    return out


def _occurrences(target: str, chars: list[tuple[str, str | None]]):
    """(class, detail) for every whole-word occurrence of the folded `target` in one line."""
    folded, idx = [], []
    for i, (ch, _) in enumerate(chars):
        for c in fold(ch):
            folded.append(c)
            idx.append(i)
    F = "".join(folded)
    is_marker = lambda j: chars[idx[j]][1] is not None
    for m in re.finditer(re.escape(target), F):
        s, e = m.start(), m.end()
        if s > 0 and F[s - 1].isalnum() and not is_marker(s - 1):
            continue                                            # starts inside another word
        region = chars[idx[s]:idx[e - 1] + 1]
        raw = "".join(ch for ch, _ in region)
        if any(is_marker(j) for j in range(s, e)):
            body = "".join(ch for ch, ev in region if ev is None)
            sup = "".join(ch for ch, ev in region if ev is not None)
            yield "mismatch_candidate_includes_marker", {"pdf_raw": f"{body}[sup:{sup}]"}
            continue
        if e == len(F) or not F[e].isalnum():
            yield "boundary", {"pdf_raw": raw}
            continue
        if is_marker(e):
            j, run = idx[e], ""
            while j < len(chars) and chars[j][1] is not None:
                run += chars[j][0]
                j += 1
            yield "match_trailing_marker", {"pdf_raw": f"{raw}[sup:{run}]", "body": raw,
                                            "marker_evidence": chars[idx[e]][1]}
            continue
        glued = re.match(r"[\w,]+", F[e:]).group(0).rstrip(",")
        if re.fullmatch(r"\d+(,\d+)*|[a-z](,[a-z])*", glued):
            yield "ambiguous_unconfirmed_marker", {"pdf_raw": raw + glued}
        # otherwise a longer word (e.g. 'smithson'): not an occurrence of this surname


def t6_classify_surname(surname: str, lines: list[tuple[int, list]]) -> dict:
    best = {"surname": surname, "class": "mismatch_not_found", "rule": None, "page": None,
            "pdf_raw": None, "marker_evidence": None}
    target = fold(surname)
    if not target:
        return best
    for page, chars in lines:
        for cls, det in _occurrences(target, chars):
            rule = None
            if cls == "boundary":
                rule = normalization_stage(surname, det["pdf_raw"])
                cls = "match_exact" if rule == "exact" else "match_normalized"
            elif cls == "match_trailing_marker":
                rule = normalization_stage(surname, det["body"])
            if RANK[cls] > RANK[best["class"]]:
                best = {"surname": surname, "class": cls, "rule": rule, "page": page,
                        "pdf_raw": det["pdf_raw"], "marker_evidence": det.get("marker_evidence")}
    return best


_WORD = re.compile("[\\w'’\\-" + "".join(sorted(SPACING_ACCENTS)) + "]+")


def t6_author_check(authors: str, lines: list[tuple[int, list]]) -> dict:
    sn = v1.surnames(authors)
    if not sn:
        return {"T6": None, "found": 0, "total": 0, "surnames": [], "outcome": "na_authors_not_reported"}
    res = [t6_classify_surname(s, lines) for s in sn]
    pdf_words = {}
    for page, chars in lines:
        for w in _WORD.findall("".join(ch for ch, _ in chars)):
            pdf_words.setdefault(fold(w), (w, page))
    for r in res:
        if r["class"] not in MATCHED:          # audit only -- never part of the decision
            near = difflib.get_close_matches(fold(r["surname"]), list(pdf_words), n=1, cutoff=0.6)
            r["nearest_pdf_word_audit_only"] = {"word": pdf_words[near[0]][0], "page": pdf_words[near[0]][1]} if near else None
    found = sum(r["class"] in MATCHED for r in res)
    return {"T6": found / len(sn) >= v1.T6_MIN, "found": found, "total": len(sn), "surnames": res,
            "outcome": "pass" if found / len(sn) >= v1.T6_MIN else "fail"}


# --- T7 --------------------------------------------------------------------------------------
def t7_arxiv_check(candidate: str, pages: list[str]) -> dict:
    p1 = pages[0] if pages else ""
    stamps = [{"id": m.group(1), "version": m.group(2) or "", "span": m.span(), "text": " ".join(m.group(0).split())}
              for m in STAMP_RE.finditer(p1)]
    observed, seen = [], set()
    for p, text in enumerate(pages, 1):
        for m in MENTION_RE.finditer(text):
            in_stamp = p == 1 and any(a <= m.start() < b for a, b in (s["span"] for s in stamps))
            observed.append({"page": p, "id": m.group(1), "version": m.group(2) or "",
                             "kind": "page1_stamp" if in_stamp else ("page1_other" if p == 1 else "later_page"),
                             "context": " ".join(text[max(0, m.start() - 50):m.end() + 20].split())})
            seen.add((p, m.start(1)))
    for s in stamps:
        s.pop("span")
    out = {"candidate": candidate, "page1_stamps": stamps, "observed": observed}
    cand = (candidate or "").strip()
    if cand in NA_VALUES:
        return {**out, "T7": None, "outcome": "na_not_reported"}
    cm = v1.ARXIV_RE.search(cand)
    if not cm:
        return {**out, "T7": False, "outcome": "fail_candidate_unparseable"}
    base = cm.group(0)
    vm = re.search(r"v\d+$", cand)
    ver = vm.group(0) if vm else ""
    for p, text in enumerate(pages, 1):                          # bare occurrences of the candidate id
        for m in re.finditer(r"(?<![\d.])" + re.escape(base) + r"(v\d+)?(?!\d)", text):
            if (p, m.start()) not in seen:
                observed.append({"page": p, "id": base, "version": m.group(1) or "",
                                 "kind": "page1_other" if p == 1 else "later_page", "bare": True,
                                 "context": " ".join(text[max(0, m.start() - 50):m.end() + 20].split())})
    same = [s for s in stamps if s["id"] == base]
    where = sorted({o["page"] for o in observed if o["id"] == base})
    if same and (not ver or any(s["version"] == ver for s in same)):
        return {**out, "T7": True, "outcome": "pass_page1_stamp"}
    if same:
        return {**out, "T7": False, "outcome": "fail_version_differs",
                "reason": f"page-1 stamp {same[0]['id']}{same[0]['version']} vs candidate {cand}"}
    if stamps:
        return {**out, "T7": False, "outcome": "fail_page1_stamp_is_other_id",
                "reason": f"page-1 stamp is {', '.join(s['id'] + s['version'] for s in stamps)}; candidate "
                          f"{cand} occurs on pages {where or 'none'}"}
    return {**out, "T7": False, "outcome": "fail_no_page1_stamp",
            "reason": f"no arXiv stamp on page 1; candidate {cand} occurs on pages {where or 'none'}"}


# --- decision ----------------------------------------------------------------------------------
def decide_v2(t: dict) -> tuple[str, str, list[str]]:
    """Phase 2 `decide`, with an N/A title treated as neutral (see module docstring)."""
    failed = [k for k in ("T1", "T2", "T3", "T4", "T5", "T6", "T7", "T8", "T9") if t.get(k) is False]
    if not t["T1"]:
        return "MISSING", "high", failed
    if not t["T2"]:
        return "AMBIGUOUS", "high", failed
    title_ok = bool(t["T5"] or t["T5p"])
    if not title_ok and t["T9_rate"] < v1.MISMATCH_T9_MAX:
        return "MISMATCH", "medium", failed
    if not failed:
        return "MATCH_VERIFIED", "high", failed
    strong = t["T3"] and (title_ok or t["T5"] is None) and t["T9"]
    return "MATCH_WITH_DISCREPANCY", ("medium" if strong else "low"), failed


def _fmt(v) -> str:
    return "N/A" if v is None else ("PASS" if v is True else ("FAIL" if v is False else str(v)))


# --- run -----------------------------------------------------------------------------------------
def main() -> None:
    pymupdf.TOOLS.mupdf_display_errors(False)
    v1_rows = {r["paper_id"]: r for r in csv.DictReader(open(V1_CSV, encoding="utf-8"))}
    v1_det = {p["paper_id"]: p for p in json.loads(V1_JSON.read_text(encoding="utf-8"))["papers"]}
    v1_hashes = {"pdf_identity_manifest.csv": v1.sha256_file(V1_CSV), "pdf_identity_details.json": v1.sha256_file(V1_JSON),
                 "phase2_pdf_identity.py": v1.sha256_file(HERE / "phase2_pdf_identity.py")}

    # pre-run gate: every Phase 2 copy exists and is byte-identical to Phase 2
    prerun, problems = [], []
    for pid in sorted(v1_rows):
        for c in v1_det[pid]["copies"]:
            p = Path(c["path"])
            h = v1.sha256_file(p) if p.is_file() else None
            prerun.append({"paper_id": pid, "path": c["path"], "exists": h is not None, "sha256": h,
                           "phase2_sha256": c["sha256"], "match": h == c["sha256"]})
            if h != c["sha256"]:
                problems.append(f"{pid}: {c['path']} exists={h is not None} hash_match={h == c['sha256']}")
        if not Path(v1_rows[pid]["canonical_pdf_path"]).is_file():
            problems.append(f"{pid}: canonical PDF missing")
    if len(v1_rows) != 30 or problems:
        sys.exit("PRE-RUN GATE FAILED -- nothing written:\n" + "\n".join(problems or [f"{len(v1_rows)} papers"]))

    zip_before = v1.sha256_file(v1.ZIP)
    zf = zipfile.ZipFile(v1.ZIP)
    papers = [json.loads(zf.read(n)) for n in sorted(zf.namelist()) if re.fullmatch(r"P\d{3}\.json", n)]
    acq = {r["paperId"]: r for r in json.loads(v1.ACQ.read_text(encoding="utf-8"))}

    rows, details, guard_failures = [], [], []
    for d in papers:
        pid, fname, meta = d["paper_id"], d["source_filename"], d["01_metadata"]
        r1 = v1_rows[pid]
        canonical = r1["canonical_pdf_path"]
        copies = [x for x in prerun if x["paper_id"] == pid]
        sha = next(x["sha256"] for x in copies if x["path"] == canonical)
        rec = acq.get(fname[:-4].lower())
        with pymupdf.open(canonical) as doc:
            n = doc.page_count
            raw_pages = [pg.get_text() for pg in doc]
            rects = [(pg.rect, pg.rotation) for pg in doc]
            lines = pdf_lines(doc, pages=2)
        pages = [v1.norm(x) for x in raw_pages]
        docn = "".join(pages)
        head = raw_pages[0] + "\n" + (raw_pages[1] if n > 1 else "")

        # unchanged Phase 2 checks, same code as phase2_pdf_identity.main
        t = {"T1": True, "T2": len({x["sha256"] for x in copies}) == 1,
             "T3": bool(rec and rec.get("document_sha256") == sha), "T4": n == meta["pages"]}
        me = meta["evidence"]
        me_loc = v1.locate(v1.norm(me["source_text"]), pages, docn, me["page"])
        t["T8"] = me_loc[0] == "stated"
        chk, found = 0, 0
        stated = 0
        for s in v1.NONCLAIM_SECTIONS:
            for e in d[s]["evidence"]:
                snn = v1.norm(e["source_text"])
                if len(snn) < v1.MIN_SNIPPET:
                    continue
                res, _ = v1.locate(snn, pages, docn, e["page"])
                chk += 1
                found += res in ("stated", "adjacent", "elsewhere")
                stated += res == "stated"
        t["T9_rate"] = found / chk if chk else 0.0
        t["T9"] = t["T9_rate"] >= v1.T9_MIN if chk else False
        refs = [me["page"]] + [e["page"] for s in v1.ALL_SECTIONS for e in d[s]["evidence"]]
        tg, ctl = d["TABLE_GROUND_TRUTH"], d["CLAIM_TABLE_LINKING"]
        refs += [x["page"] for x in tg["tables"]] + [x["page"] for x in tg["table_inventory"]] + [x["page"] for x in tg["cells"]]
        refs += [x["page"] for x in ctl["cross_references"]] + [x["evidence_page"] for x in ctl["claim_table_relationships"]]
        refs += [x["page"] for x in d["numeric_normalization_cases"]]
        oor = sum(not (isinstance(p, int) and 1 <= p <= n) for p in refs)
        inside, within = 0, 0
        for tb in tg["tables"]:
            p, b = tb["page"], tb["bbox"]
            if 1 <= p <= n:
                within += 1
                rect = rects[p - 1][0]
                inside += (b[0] >= rect.x0 - v1.BBOX_TOL and b[1] >= rect.y0 - v1.BBOX_TOL and
                           b[2] <= rect.x1 + v1.BBOX_TOL and b[3] <= rect.y1 + v1.BBOX_TOL)
        recomputed = {"sha256": sha, "copies_byte_identical": str(t["T2"]), "acquisition_sha256_match": str(t["T3"]),
                      "pdf_page_count": str(n), "page_count_match": str(t["T4"]), "metadata_evidence_location": me_loc[0],
                      "evidence_snippets_checkable": str(chk), "evidence_found_anywhere": str(found),
                      "evidence_found_on_stated_page": str(stated), "candidate_page_refs": str(len(refs)),
                      "candidate_page_refs_out_of_range": str(oor),
                      "table_pages_within_pdf": f"{within}/{len(tg['tables'])}",
                      "table_bbox_inside_page": f"{inside}/{len(tg['tables'])}"}
        diffs = {k: (r1[k], recomputed[k]) for k in UNCHANGED_FIELDS if r1[k] != recomputed[k]}
        if diffs:
            guard_failures.append(f"{pid}: {diffs}")

        # corrected checks
        t5 = t5_title_check(meta["title"], head)
        t6 = t6_author_check(meta["authors"], lines)
        t7 = t7_arxiv_check(meta["arxiv_id"], raw_pages)
        t.update(T5=t5["T5"], T5p=t5["T5p"], T6=t6["T6"], T7=t7["T7"])
        status, conf, failed = decide_v2(t)
        classes = Counter(s["class"] for s in t6["surnames"])
        row = {
            "paper_id": pid, "json_filename": f"{pid}.json", "pdf_filename": fname, "canonical_pdf_path": canonical,
            "sha256": sha, "prerun_copies_verified": f"{sum(x['match'] for x in copies)}/{len(copies)}",
            **{f"check_{k}": _fmt(t[k]) for k in ("T1", "T2", "T3", "T4", "T5", "T6", "T7", "T8", "T9")},
            "identity_status_v2": status, "checks_failed_v2": ";".join(failed), "verification_confidence_v2": conf,
            "verification_method": "normalized", "identity_status_phase2": r1["identity_status"],
            "checks_failed_phase2": r1["checks_failed"], "status_changed": status != r1["identity_status"],
            "candidate_title": meta["title"], "t5_outcome": t5["outcome"],
            "t5_title_word_coverage": "" if t5["coverage"] is None else round(t5["coverage"], 3),
            "candidate_authors": meta["authors"], "t6_outcome": t6["outcome"],
            "t6_surnames_found": f"{t6['found']}/{t6['total']}" if t6["total"] else "N/A",
            "t6_class_counts": ";".join(f"{k}:{v}" for k, v in sorted(classes.items())),
            "t6_non_matched": ";".join(f"{s['surname']}({s['class']})" for s in t6["surnames"] if s["class"] not in MATCHED),
            "candidate_arxiv_id": meta["arxiv_id"], "t7_outcome": t7["outcome"],
            "page1_arxiv_stamps": ";".join(s["id"] + s["version"] for s in t7["page1_stamps"]),
            "candidate_arxiv_pages": ";".join(str(p) for p in sorted({o["page"] for o in t7["observed"]
                                                                       if o["id"] == (v1.ARXIV_RE.search(meta["arxiv_id"] or "") or [None])[0]})),
            "t9_rate": round(t["T9_rate"], 3),
            **{k: recomputed[k] for k in UNCHANGED_FIELDS if k != "sha256"},
            "unchanged_checks_equal_phase2": not diffs,
        }
        rows.append(row)
        details.append({"paper_id": pid, "checks": t, "status": status, "confidence": conf, "failed": failed,
                        "phase2_status": r1["identity_status"], "t5": t5, "t6": t6, "t7": t7,
                        "prerun_copies": copies, "unchanged_check_diffs": diffs,
                        "t9": {"checkable": chk, "found": found, "on_stated_page": stated}})

    if guard_failures:
        sys.exit("UNCHANGED-CHECK GUARD FAILED -- Phase 2.1 does not reproduce Phase 2; nothing written:\n"
                 + "\n".join(guard_failures))
    zip_after = v1.sha256_file(v1.ZIP)
    post = {x["path"]: v1.sha256_file(Path(x["path"])) for x in prerun}
    hashes_stable = all(post[x["path"]] == x["sha256"] for x in prerun)
    v1_untouched = v1_hashes == {"pdf_identity_manifest.csv": v1.sha256_file(V1_CSV),
                                 "pdf_identity_details.json": v1.sha256_file(V1_JSON),
                                 "phase2_pdf_identity.py": v1.sha256_file(HERE / "phase2_pdf_identity.py")}

    with open(OUT_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    prov = {"phase": "2.1", "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "script": "src/evaluation/bottleneck_diagnosis/phase2_1_pdf_identity.py",
            "git_head": v1.git("rev-parse", "HEAD"), "git_branch": v1.git("rev-parse", "--abbrev-ref", "HEAD"),
            "python": sys.version.split()[0], "pymupdf": pymupdf.VersionBind, "platform": platform.platform(),
            "zip_sha256_before": zip_before, "zip_sha256_after": zip_after, "pdf_hashes_stable": hashes_stable,
            "phase2_artifact_sha256": v1_hashes, "phase2_artifacts_unchanged": v1_untouched,
            "acquisition_record_sha256": v1.sha256_file(v1.ACQ)}
    OUT_JSON.write_text(json.dumps({"artifact": "pdf_identity_details_v2", "provenance": prov,
                                    "rules": __doc__, "prerun": prerun, "papers": details},
                                   indent=1, ensure_ascii=False, default=str), encoding="utf-8")
    OUT_MD.write_text(report(rows, details, prov, prerun), encoding="utf-8")

    print(f"wrote {OUT_CSV.name}, {OUT_JSON.name}, {OUT_MD.name}")
    print(f"pre-run: {sum(x['match'] for x in prerun)}/{len(prerun)} copies verified | unchanged checks equal Phase 2: 30/30 "
          f"| zip unchanged: {zip_before == zip_after} | pdf hashes stable: {hashes_stable} | Phase 2 artifacts unchanged: {v1_untouched}")
    print("status v2:", dict(Counter(r["identity_status_v2"] for r in rows)))
    for r in rows:
        print(f"{r['paper_id']} {r['identity_status_v2']:<23} {r['verification_confidence_v2']:<6} T5={r['check_T5']:<4} "
              f"T6={r['check_T6']:<4} {r['t6_surnames_found']:<6} T7={r['check_T7']:<4} {r['t7_outcome']:<30} "
              f"non-matched=[{r['t6_non_matched']}]")


def report(rows: list[dict], details: list[dict], prov: dict, prerun: list[dict]) -> str:
    det = {d["paper_id"]: d for d in details}
    st = Counter(r["identity_status_v2"] for r in rows)
    L = ["# Phase 2.1 — corrected PDF identity evaluation",
         "",
         "**These are Phase 2.1 corrected outputs** (evaluator-only fix of T5, T6, T7). The Phase 2 outputs are",
         "preserved unchanged and remain the record of the original rule:",
         "",
         "| Phase 2 artifact (unchanged) | SHA-256 |", "|---|---|"]
    L += [f"| `{k}` | `{v}` |" for k, v in prov["phase2_artifact_sha256"].items()]
    L += ["", f"Phase 2 artifacts byte-identical after this run: **{prov['phase2_artifacts_unchanged']}**.", "",
          "| | |", "|---|---|",
          f"| Evaluator | `{prov['script']}` (imports every unchanged helper and threshold from `phase2_pdf_identity.py`) |",
          "| Outputs | `pdf_identity_manifest_v2.csv`, `pdf_identity_details_v2.json`, this report |",
          f"| Run | {prov['generated_at_utc']}, git `{prov['git_head'][:12]}` (`{prov['git_branch']}`), Python {prov['python']}, PyMuPDF {prov['pymupdf']} |",
          "| Command | `PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe src/evaluation/bottleneck_diagnosis/phase2_1_pdf_identity.py` |",
          "| Tests | `.venv/Scripts/python.exe -m pytest -p no:cacheprovider src/evaluation/bottleneck_diagnosis/test_phase2_1_pdf_identity.py -q` |",
          "", "## 1. What changed (and what did not)", "",
          "| Check | Phase 2 rule | Phase 2.1 rule |", "|---|---|---|",
          "| T5 title | A candidate title of `NOT_REPORTED` was compared as if it were a title (a false FAIL) | `NOT_REPORTED` or empty gives **N/A**. Reported titles use the unchanged rule |",
          "| T6 authors | Page tokens kept affiliation superscripts glued to surnames (`comte1`), causing false FAILs | Whole-word surname match on the PyMuPDF span stream. A trailing marker is accepted only if the PDF marks it as superscript (MuPDF flag, or smaller and raised span, or Unicode superscript). Normalization stages are recorded per surname |",
          "| T7 arXiv | The candidate id found **anywhere** passed, including reference lists (false PASSes) | The candidate id passes **only** if it equals the page-1 arXiv stamp `arXiv:<id>[vN] [cat]`; other occurrences are kept for audit |",
          "| decide | An N/A title counted as a title failure in the confidence clause | N/A title is neutral; otherwise unchanged |",
          "",
          "Unchanged and re-verified for all 30 papers: T1–T4, T8, T9, all thresholds, and the candidate-consistency",
          "checks C1/C2. The run aborts unless these reproduce the Phase 2 values exactly; they did (30/30).",
          "",
          "## 2. Pre-run verification (no substitution)", "",
          f"- {len(prerun)} PDF copies recorded in Phase 2 across 30 papers. {sum(x['exists'] for x in prerun)} exist, and "
          f"{sum(x['match'] for x in prerun)} hash to the Phase 2 SHA-256. They were re-hashed after the run: stable = **{prov['pdf_hashes_stable']}**.",
          f"- No PDF was downloaded, searched for or substituted. Candidate ZIP SHA-256 is unchanged: "
          f"**{prov['zip_sha256_before'] == prov['zip_sha256_after']}** (`{prov['zip_sha256_after'][:16]}…`).",
          "", "## 3. Summary", "",
          f"- Papers: **{len(rows)}**. **MATCH_VERIFIED {st.get('MATCH_VERIFIED', 0)}**, "
          f"**MATCH_WITH_DISCREPANCY {st.get('MATCH_WITH_DISCREPANCY', 0)}**. MISMATCH {st.get('MISMATCH', 0)}, "
          f"AMBIGUOUS {st.get('AMBIGUOUS', 0)}, MISSING {st.get('MISSING', 0)}.", "",
          "| Test | PASS | FAIL | N/A |", "|---|---|---|---|"]
    for k in ("T1", "T2", "T3", "T4", "T5", "T6", "T7", "T8", "T9"):
        c = Counter(r[f"check_{k}"] for r in rows)
        L.append(f"| {k} | {c.get('PASS', 0)} | {c.get('FAIL', 0)} | {c.get('N/A', 0)} |")
    tr = Counter((r["identity_status_phase2"], r["identity_status_v2"]) for r in rows)
    L += ["", "Status transitions, Phase 2 → Phase 2.1:", "", "| Phase 2 | Phase 2.1 | Papers |", "|---|---|---|"]
    L += [f"| {a} | {b} | {n} |" for (a, b), n in sorted(tr.items())]
    L += ["", "## 4. Every remaining discrepancy", "",
          "| paper_id | test | candidate value | PDF-observed value | page | reason | normalization / rule |",
          "|---|---|---|---|---|---|---|"]
    n_disc = 0
    for r in rows:
        d = det[r["paper_id"]]
        for k in d["failed"]:
            n_disc += 1
            if k == "T7":
                t7 = d["t7"]
                obs = "; ".join(sorted({f"{o['id']}{o['version']} ({o['kind']}, p{o['page']})" for o in t7["observed"]})) or "no arXiv id in text"
                stamp = ", ".join(s["id"] + s["version"] for s in t7["page1_stamps"]) or "none on page 1"
                pgs = ",".join(str(p) for p in sorted({o["page"] for o in t7["observed"] if o["id"] in r["candidate_arxiv_id"]}))
                L.append(f"| {r['paper_id']} | T7 | `{r['candidate_arxiv_id']}` | page-1 stamp: {stamp}; observed: {obs} | "
                         f"{pgs or '—'} | {t7.get('reason', t7['outcome'])} | page-1 arXiv stamp only |")
            elif k == "T6":
                t6 = d["t6"]
                bad = [s for s in t6["surnames"] if s["class"] not in MATCHED]
                obs = "; ".join(f"{s['surname']}→{(s.get('nearest_pdf_word_audit_only') or {}).get('word', '—')}" for s in bad)
                L.append(f"| {r['paper_id']} | T6 | {t6['found']}/{t6['total']} surnames matched | {obs} | 1–2 | "
                         f"found fraction below {v1.T6_MIN} | span-stream whole-word match |")
            elif k == "T5":
                L.append(f"| {r['paper_id']} | T5 | `{r['candidate_title'][:80]}` | title not a substring of pages 1–2 | 1–2 | "
                         f"word coverage {r['t5_title_word_coverage']} | normalized substring (unchanged) |")
            else:
                L.append(f"| {r['paper_id']} | {k} | see manifest | see manifest | — | {k} failed | unchanged Phase 2 rule |")
    if not n_disc:
        L.append("| — | — | — | — | — | none | — |")
    L += ["", "## 5. Surname-level non-matches inside papers where T6 passes", "",
          "These do not fail T6 at the unchanged 0.5 threshold. They are listed so that no candidate author error is hidden.",
          "", "| paper_id | candidate surname | class | PDF-observed (audit) | page |", "|---|---|---|---|---|"]
    k = 0
    for r in rows:
        for s in det[r["paper_id"]]["t6"]["surnames"]:
            if s["class"] not in MATCHED and "T6" not in det[r["paper_id"]]["failed"]:
                k += 1
                near = s.get("nearest_pdf_word_audit_only") or {}
                obs = s["pdf_raw"] or (f"nearest word: {near.get('word')}" if near else "—")
                L.append(f"| {r['paper_id']} | {s['surname']} | {s['class']} | {obs} | {s['page'] or near.get('page') or '—'} |")
    if not k:
        L.append("| — | — | none | — | — |")
    allc = Counter(s["class"] for d in details for s in d["t6"]["surnames"])
    rules = Counter(s["rule"] for d in details for s in d["t6"]["surnames"] if s["class"] in MATCHED)
    ev = Counter(s["marker_evidence"] for d in details for s in d["t6"]["surnames"] if s["class"] == "match_trailing_marker")
    L += ["", "## 6. T6 detail (all candidate surnames)", "",
          f"- Surnames checked: {sum(allc.values())}. By class: " + ", ".join(f"{c} {n}" for c, n in allc.most_common()) + ".",
          "- Normalization stage that made each match: " + ", ".join(f"{c} {n}" for c, n in rules.most_common()) + ".",
          "- Evidence for trailing affiliation markers: " + (", ".join(f"{c} {n}" for c, n in ev.most_common()) or "none") + ".",
          "- The per-surname record (class, stage, raw PDF text with `[sup:…]` markers, page) is in `pdf_identity_details_v2.json` → `papers[].t6`.",
          "", "## 7. T7 detail (papers that report an arXiv id)", "",
          "| paper_id | candidate | page-1 stamp | outcome |", "|---|---|---|---|"]
    for r in rows:
        if r["candidate_arxiv_id"] not in NA_VALUES:
            L.append(f"| {r['paper_id']} | `{r['candidate_arxiv_id']}` | {r['page1_arxiv_stamps'] or 'none'} | {r['t7_outcome']} |")
    nst = [r["paper_id"] for r in rows if r["candidate_arxiv_id"] in NA_VALUES and r["page1_arxiv_stamps"]]
    L += ["", f"Papers whose candidate reports no arXiv id but whose page 1 carries a stamp (T7 is N/A; informational): "
              f"{', '.join(nst) or 'none'}.", ""]
    return "\n".join(L) + "\n"


if __name__ == "__main__":
    main()
