"""Phase 1 -- inventory and validate the candidate-gold ZIP, read-only.

    .venv/Scripts/python.exe src/evaluation/bottleneck_diagnosis/phase1_candidate_gold_inventory.py

The ZIP is opened in place and never extracted, moved or written. Every count in the
output is measured from the paper JSON members; INDEX.json and each paper's
extraction_audit are compared against the measurement, never trusted.

Checks named `*(heuristic)` are flags for Phase 3 planning, not verdicts: only the
physical PDF can verify a candidate pair. The PDF section is a filename-presence
check only (identity, hashes and page counts are Phase 2).
"""
from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import subprocess
import sys
import zipfile
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
ZIP = ROOT / "src" / "evaluation" / "candidate_gold" / "researchgpt_candidate_gold_30_2026-09-28 (1).zip"
OUT = HERE / "candidate_gold_inventory.json"
MAX_EXAMPLES = 25
LEGIT_MARKERS = set("*†‡§¶∗#")
NUM = re.compile(r"\d+(?:\.\d+)?")
SENTINEL = "NOT_REPORTED"
SECTIONS = ["02_research_problem", "03_research_objective", "04_methodology", "05_dataset",
            "06_preprocessing", "07_experimental_setup", "08_baselines_and_comparisons",
            "09_evaluation_metrics", "10_quantitative_results", "11_qualitative_results",
            "12_claims_and_conclusions", "13_limitations"]
PDF_WALK_SKIP = {".git", ".venv", "node_modules", "__pycache__", "chroma_db", "chroma_users", "figures"}

ISSUES: dict[str, list] = defaultdict(list)


def issue(check: str, pid: str, **kw) -> None:
    ISSUES[check].append({"paper_id": pid, **kw})


def sha256(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def git(*args: str) -> str:
    try:
        return subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True,
                              text=True, check=True).stdout.strip()
    except Exception as e:  # recorded, not fatal
        return f"UNAVAILABLE: {e}"


def norm_label(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower()).rstrip(".:")


def nums(s: str) -> list[str]:
    return NUM.findall(s or "")


def structural_only(tok: str, text: str) -> bool:
    """heuristic: every whole-token occurrence of `tok` in `text` is a table/figure/section
    number, a bracket citation, a year, or the claim's leading heading number."""
    occ = [m for m in NUM.finditer(text or "") if m.group() == tok]
    def structural(m):
        before, after = text[:m.start()], text[m.end():]
        return bool(re.search(r"(?:tables?|fig(?:ure)?s?\.?|sec(?:tion)?\.?|eq(?:uation)?\.?)\s*$", before, re.I)
                    or re.search(r"\[[\d,\s–-]*$", before) and re.match(r"[\d,\s–-]*\]", after)
                    or re.fullmatch(r"(?:19|20)\d\d", tok)
                    or not before.strip() and re.match(r"\.?\s+[A-Z]", after))
    return bool(occ) and all(structural(m) for m in occ)


def label_in_text(label: str, text: str) -> bool:
    """Whole-token match of a printed label ('Table 3', 'Table IV') in free text."""
    m = re.fullmatch(r"\s*table\s+([0-9]+|[ivxlcdm]+|[a-z])\s*", label or "", re.I)
    if not m:
        return False
    return re.search(rf"\btables?\s*{re.escape(m.group(1))}\b", text or "", re.I) is not None


def walk(x, path, pid, types, present, keysets):
    types[path][type(x).__name__] += 1
    present[path].add(pid)
    if isinstance(x, dict):
        keysets[path][tuple(sorted(x))] += 1
        for k, v in x.items():
            walk(v, f"{path}.{k}", pid, types, present, keysets)
    elif isinstance(x, list):
        for v in x:
            walk(v, f"{path}[]", pid, types, present, keysets)


def pdf_presence(filenames: list[str]) -> dict:
    """Exact (case-insensitive) filename presence across this repo's git worktrees."""
    roots = [Path(l[len("worktree "):]) for l in git("worktree", "list", "--porcelain").splitlines()
             if l.startswith("worktree ")] or [ROOT]
    want = {f.lower() for f in filenames}
    hits: dict[str, list] = defaultdict(list)
    for root in roots:
        for dp, dns, fns in os.walk(root):
            dns[:] = [d for d in dns if d not in PDF_WALK_SKIP]
            for fn in fns:
                if fn.lower() in want:
                    p = Path(dp) / fn
                    hits[fn.lower()].append({"path": str(p), "size_bytes": p.stat().st_size})
    return {"method": "exact filename, case-insensitive; no hashing, page counting or identity check (Phase 2)",
            "roots_searched": [str(r) for r in roots], "skipped_dir_names": sorted(PDF_WALK_SKIP),
            "hits": {f: hits.get(f.lower(), []) for f in filenames}}


def main() -> None:
    raw_zip = ZIP.read_bytes()
    zf = zipfile.ZipFile(ZIP)
    members, docs = [], {}
    for info in zf.infolist():
        b = zf.read(info.filename)
        rec = {"name": info.filename, "file_size": info.file_size, "compress_size": info.compress_size,
               "crc32": f"{info.CRC:08x}", "sha256": sha256(b), "utf8_bom": b.startswith(b"\xef\xbb\xbf")}
        try:
            text = b.decode("utf-8")
            rec["utf8_valid"] = True
        except UnicodeDecodeError as e:
            rec["utf8_valid"], text = False, None
            issue("json.utf8_invalid", info.filename, error=str(e))
        if info.filename.endswith(".json") and text is not None:
            try:
                docs[info.filename] = json.loads(text)
                rec["json_valid"] = True
            except json.JSONDecodeError as e:
                rec["json_valid"] = False
                issue("json.syntax_error", info.filename, error=str(e))
        members.append(rec)

    names = [m["name"] for m in members]
    paper_files = sorted(n for n in names if re.fullmatch(r"P\d{3}\.json", n))
    expected = [f"P{i:03d}.json" for i in range(1, len(paper_files) + 1)]
    unexpected = sorted(set(names) - set(paper_files) - {"INDEX.json", "README.txt"})
    index = docs.get("INDEX.json", {})
    readme = zf.read("README.txt").decode("utf-8") if "README.txt" in names else None
    idx_by_pid = {e["paper_id"]: e for e in index.get("papers", [])}

    # ---- schema: union of key paths, key-set variants, type variants ----
    types, present, keysets = defaultdict(Counter), defaultdict(set), defaultdict(Counter)
    for fn in paper_files:
        walk(docs[fn], "$", fn[:-5], types, present, keysets)
    for path, variants in keysets.items():
        if len(variants) > 1:
            union = set().union(*map(set, variants))
            issue("schema.keyset_variants", "*", path=path,
                  variants=[{"n": n, "missing": sorted(union - set(ks))} for ks, n in variants.items()])
    type_variants = {}
    for path, tc in types.items():
        t = set(tc) - {"NoneType"}
        if {"int", "float"} <= t:
            t = (t - {"int", "float"}) | {"number"}
        if len(t) > 1:
            type_variants[path] = dict(tc)
            issue("schema.type_variants", "*", path=path, types=dict(tc))

    papers, table_rows, pair_rows = [], [], []
    dist = defaultdict(Counter)
    totals = Counter()

    for fn in paper_files:
        d = docs[fn]
        pid = d["paper_id"]
        if pid != fn[:-5]:
            issue("ref.paper_id_vs_filename", pid, json_filename=fn)
        meta, tg, ctl, audit = d["01_metadata"], d["TABLE_GROUND_TRUTH"], d["CLAIM_TABLE_LINKING"], d["extraction_audit"]
        tables, inv, cells = tg["tables"], tg["table_inventory"], tg["cells"]
        q, cc = d["10_quantitative_results"]["evidence"], d["12_claims_and_conclusions"]["evidence"]
        pairs, rels, xrefs = ctl["gold_claim_cell_pairs"], ctl["claim_table_relationships"], ctl["cross_references"]
        ncases = d["numeric_normalization_cases"]
        npages = meta["pages"]

        # claims: sections 10 and 12 both carry claim_id; measure whether they are the same list
        sections_identical = q == cc
        claims = {e["claim_id"]: e for e in q}
        for e in cc:
            claims.setdefault(e["claim_id"], e)
        if not sections_identical:
            issue("ref.claim_sections_10_12_differ", pid, n10=len(q), n12=len(cc))

        # ---- duplicates ----
        def dups(check, ids):
            for k, n in Counter(ids).items():
                if n > 1:
                    issue(check, pid, id=k, occurrences=n)
        dups("dup.table_id(tables)", [t["table_id"] for t in tables])
        dups("dup.table_id(table_inventory)", [t["table_id"] for t in inv])
        dups("dup.cell_id", [c["cell_id"] for c in cells])
        dups("dup.cell_position", [f'{c["table_id"]}/R{c["row_index"]}/C{c["column_index"]}' for c in cells])
        dups("dup.claim_id(10_quantitative_results)", [e["claim_id"] for e in q])
        dups("dup.claim_id(12_claims_and_conclusions)", [e["claim_id"] for e in cc])
        dups("dup.claim_text(distinct claim_ids, identical source_text)", [e["source_text"] for e in claims.values()])
        dups("dup.pair_id", [p["pair_id"] for p in pairs])
        dups("dup.relationship_id", [r["relationship_id"] for r in rels])
        dups("dup.cross_reference_id", [x["cross_reference_id"] for x in xrefs])
        dups("dup.case_id", [n["case_id"] for n in ncases])
        dups("ambig.duplicate_printed_label_in_paper", [norm_label(t["printed_label"]) for t in tables])

        # ---- reference integrity ----
        table_by = {t["table_id"]: t for t in tables}
        inv_by = {t["table_id"]: t for t in inv}
        cell_by = {c["cell_id"]: c for c in cells}
        labels = defaultdict(list)
        for t in tables:
            labels[norm_label(t["printed_label"])].append(t["table_id"])

        for c in cells:
            if c["table_id"] not in table_by:
                issue("ref.cell_table_id_missing", pid, cell_id=c["cell_id"], table_id=c["table_id"])
            m = re.fullmatch(r"(T\d+)_R(\d+)_C(\d+)", c["cell_id"])
            if not m or (m[1], int(m[2]), int(m[3])) != (c["table_id"], c["row_index"], c["column_index"]):
                issue("ref.cell_id_vs_fields", pid, cell_id=c["cell_id"])

        rel_labels_by_claim = defaultdict(set)
        for r in rels:
            rel_labels_by_claim[r["claim_id"]].add(norm_label(r["table_label"]))
            if r["claim_id"] not in claims:
                issue("ref.relationship_claim_missing", pid, relationship_id=r["relationship_id"], claim_id=r["claim_id"])
            if r["table_id"] is None:
                issue("ref.relationship_table_id_null", pid, relationship_id=r["relationship_id"], table_label=r["table_label"])
            hits = labels.get(norm_label(r["table_label"]), [])
            if not hits:
                issue("ref.relationship_label_unresolvable", pid, relationship_id=r["relationship_id"], table_label=r["table_label"])
            elif len(hits) > 1:
                issue("ambig.relationship_label_multiple_tables", pid, relationship_id=r["relationship_id"],
                      table_label=r["table_label"], table_ids=hits)
            if r["evidence_page"] is not None and not (1 <= r["evidence_page"] <= npages):
                issue("page.out_of_range", pid, where="relationship.evidence_page", id=r["relationship_id"], page=r["evidence_page"], pages=npages)

        xref_resolution = Counter()
        for x in xrefs:
            hits = labels.get(norm_label(x["normalized_table_label"]), [])
            xref_resolution["resolves_to_0_tables" if not hits else "resolves_to_1_table" if len(hits) == 1 else "resolves_to_2+_tables"] += 1
            if not hits:
                issue("ref.cross_reference_label_unresolvable", pid, cross_reference_id=x["cross_reference_id"],
                      label=x["normalized_table_label"])
            if not x["resolved"]:
                issue("ambig.cross_reference_marked_unresolved", pid, cross_reference_id=x["cross_reference_id"])

        for n in ncases:
            c = cell_by.get(n["cell_id"])
            if c is None:
                issue("ref.numeric_case_cell_missing", pid, case_id=n["case_id"], cell_id=n["cell_id"])
                continue
            for k_case, k_cell in (("table_id", "table_id"), ("page", "page"), ("raw_text", "raw_text"),
                                   ("normalized_value", "numeric_value"), ("uncertainty", "uncertainty"), ("unit", "unit")):
                if n[k_case] != c[k_cell]:
                    issue("ref.numeric_case_vs_cell_field_mismatch", pid, case_id=n["case_id"], cell_id=n["cell_id"],
                          field=k_case, case_value=n[k_case], cell_value=c[k_cell])

        # ---- tables: inventory agreement, grid/cell consistency, coordinates, content ----
        for t in inv:
            if t["table_id"] not in table_by:
                issue("count.inventory_table_missing_from_tables", pid, table_id=t["table_id"])
        cells_by_table = defaultdict(list)
        for c in cells:
            cells_by_table[c["table_id"]].append(c)
        num_index = defaultdict(list)          # numeric_value -> cell_ids (paper-wide)
        for c in cells:
            if c["numeric_value"] is not None:
                num_index[c["numeric_value"]].append(c["cell_id"])

        for t in tables:
            tid, oc, hh = t["table_id"], t["original_contents"], t["header_hierarchy"]
            i = inv_by.get(tid)
            if i is None:
                issue("count.table_missing_from_inventory", pid, table_id=tid)
            else:
                for k in ("printed_label", "caption", "page", "bbox"):
                    if t[k] != i[k]:
                        issue("count.table_vs_inventory_field_mismatch", pid, table_id=tid, field=k)
            widths = sorted({len(r) for r in oc})
            if t["rows"] != len(oc):
                issue("count.rows_vs_original_contents", pid, table_id=tid, rows=t["rows"], oc_rows=len(oc))
            if len(widths) > 1:
                issue("count.ragged_original_contents", pid, table_id=tid, row_widths=widths)
            if oc and t["cols"] != max(widths):
                issue("count.cols_vs_original_contents", pid, table_id=tid, cols=t["cols"], oc_max_width=max(widths))
            if t["page"] != t["source_evidence"]["page"]:
                issue("count.table_page_vs_source_evidence_page", pid, table_id=tid)
            if t["caption"] != t["source_evidence"]["caption_text"]:
                issue("count.caption_vs_source_evidence_caption", pid, table_id=tid)
            if not (1 <= t["page"] <= npages):
                issue("page.out_of_range", pid, where="table.page", id=tid, page=t["page"], pages=npages)

            b = t["bbox"]
            if len(b) != 4 or not all(isinstance(v, (int, float)) for v in b):
                issue("coord.bbox_malformed", pid, table_id=tid, bbox=b)
            else:
                x0, y0, x1, y1 = b
                if x0 >= x1 or y0 >= y1:
                    issue("coord.bbox_non_positive_extent", pid, table_id=tid, bbox=b)
                if min(b) < 0:
                    issue("coord.bbox_negative", pid, table_id=tid, bbox=b)
                if max(b) > 2000:
                    issue("coord.bbox_exceeds_2000pt", pid, table_id=tid, bbox=b)

            tc = cells_by_table.get(tid, [])
            positions = set()
            for c in tc:
                r, k = c["row_index"], c["column_index"]
                positions.add((r, k))
                if not (1 <= r <= len(oc)) or not (1 <= k <= len(oc[r - 1])):
                    issue("count.cell_index_outside_original_contents", pid, cell_id=c["cell_id"])
                elif oc[r - 1][k - 1] != c["raw_text"]:
                    issue("count.cell_raw_text_vs_original_contents", pid, cell_id=c["cell_id"],
                          cell=c["raw_text"][:60], grid=oc[r - 1][k - 1][:60])
                if c["page"] != t["page"]:
                    issue("count.cell_page_vs_table_page", pid, cell_id=c["cell_id"], cell_page=c["page"], table_page=t["page"])
            grid = [(r + 1, k + 1) for r, row in enumerate(oc) for k in range(len(row))]
            uncovered = [(r, k) for r, k in grid if (r, k) not in positions]
            uncovered_nonempty = [(r, k) for r, k in uncovered if oc[r - 1][k - 1].strip()]
            header_is_row1 = isinstance(hh, list) and bool(oc) and hh == oc[0]
            n_num = sum(c["numeric_value"] is not None for c in tc)
            frac = n_num / len(tc) if tc else 0.0
            if tc and frac < 0.1:
                issue("content.table_numeric_fraction_below_0.1(heuristic: possible non-table text region)", pid,
                      table_id=tid, printed_label=t["printed_label"], numeric_fraction=round(frac, 3))
            if not t["caption"].lower().startswith(t["printed_label"].lower()):
                issue("content.caption_not_starting_with_printed_label", pid, table_id=tid,
                      printed_label=t["printed_label"], caption=t["caption"][:80])
            if t["caption"].rstrip().endswith("-"):
                issue("content.caption_ends_with_hyphen(heuristic: truncated)", pid, table_id=tid, caption=t["caption"][-60:])
            dist["table.header_hierarchy_type"][type(hh).__name__ if not isinstance(hh, str) else f"str:{hh}"] += 1
            table_rows.append({
                "paper_id": pid, "table_id": tid, "printed_label": t["printed_label"], "page": t["page"],
                "bbox": t["bbox"], "rows": t["rows"], "cols": t["cols"], "oc_rows": len(oc), "oc_row_widths": widths,
                "grid_positions": len(grid), "grid_nonempty": sum(1 for r, k in grid if oc[r - 1][k - 1].strip()),
                "n_cells": len(tc), "grid_positions_without_cell": len(uncovered),
                "nonempty_grid_positions_without_cell": len(uncovered_nonempty),
                "row1_positions_without_cell": sum(1 for r, _ in uncovered if r == 1),
                "header_hierarchy_type": type(hh).__name__, "header_hierarchy_equals_row1": header_is_row1,
                "n_numeric_cells": n_num, "numeric_fraction": round(frac, 3),
                "caption": t["caption"][:160],
            })

        # ---- cells: content checks ----
        for c in cells:
            rt, nt = c["raw_text"], c["normalized_text"]
            dist["cell.cell_type"][c["cell_type"]] += 1
            dist["cell.header_path_len"][len(c["header_path"])] += 1
            for k in ("row_label", "column_label"):
                dist[f"cell.{k}"]["NOT_REPORTED" if c[k] == SENTINEL else "empty_string" if c[k] == "" else "value"] += 1
            if c["unit"]:
                dist["cell.unit"][c["unit"]] += 1
            if rt != nt:
                issue("content.raw_text_differs_from_normalized_text", pid, cell_id=c["cell_id"], raw=rt[:60], normalized=nt[:60])
            if "�" in rt or "�" in nt:
                issue("content.replacement_char_U+FFFD_in_cell", pid, cell_id=c["cell_id"])
            bad = [s for s in c["significance_markers"] if s not in LEGIT_MARKERS]
            if bad:
                issue("content.significance_markers_not_marker_glyphs", pid, cell_id=c["cell_id"],
                      markers=c["significance_markers"][:12], raw_text=rt[:60])
            if rt.count("±") >= 2:
                issue("content.multiple_pm_values_in_one_cell(heuristic: merged cells)", pid, cell_id=c["cell_id"], raw_text=rt[:80])
            if c["numeric_value"] is not None:
                vals = [float(x) for x in nums(nt)]
                if not any(abs(v - abs(c["numeric_value"])) < 1e-9 for v in vals):
                    issue("content.numeric_value_not_found_in_normalized_text", pid, cell_id=c["cell_id"],
                          numeric_value=c["numeric_value"], normalized_text=nt[:60])
            if (c["uncertainty"] is not None) != (c["cell_type"] == "numeric_with_uncertainty"):
                issue("content.uncertainty_vs_cell_type", pid, cell_id=c["cell_id"], cell_type=c["cell_type"])
            if "±" in rt and c["uncertainty"] is None:
                issue("content.pm_glyph_without_uncertainty", pid, cell_id=c["cell_id"], raw_text=rt[:60], cell_type=c["cell_type"])
            if c["uncertainty"] is not None and "±" not in rt:
                issue("content.uncertainty_without_pm_glyph", pid, cell_id=c["cell_id"], raw_text=rt[:60])
            if not (1 <= c["page"] <= npages):
                issue("page.out_of_range", pid, where="cell.page", id=c["cell_id"], page=c["page"], pages=npages)
            for m in c["significance_markers"]:
                dist["cell.significance_marker_item"][m] += 1

        # ---- claims ----
        for cid, e in claims.items():
            s = e["source_text"]
            if not (1 <= e["page"] <= npages):
                issue("page.out_of_range", pid, where="claim.page", id=cid, page=e["page"], pages=npages)
            if not re.search(r"\d", s):
                issue("content.claim_has_no_digit(heuristic)", pid, claim_id=cid, text=s[:100])
            if re.search(r"arXiv:\s*\d", s):
                issue("content.claim_contains_arxiv_stamp(heuristic)", pid, claim_id=cid, text=s[:100])
            if re.match(r"^\d+(\.\d+)*\.?\s+[A-Z]", s):
                issue("content.claim_starts_with_section_number(heuristic)", pid, claim_id=cid, text=s[:100])
            if len(s) < 40:
                issue("content.claim_shorter_than_40_chars(heuristic)", pid, claim_id=cid, text=s)
        for sec in SECTIONS:
            for e in d[sec]["evidence"]:
                if not (1 <= e["page"] <= npages):
                    issue("page.out_of_range", pid, where=f"{sec}.evidence.page", page=e["page"], pages=npages)
        for x in xrefs:
            if not (1 <= x["page"] <= npages):
                issue("page.out_of_range", pid, where="cross_reference.page", id=x["cross_reference_id"], page=x["page"], pages=npages)
        for n in ncases:
            dist["numeric_case.case_type"][n["case_type"]] += 1
            if not (1 <= n["page"] <= npages):
                issue("page.out_of_range", pid, where="numeric_case.page", id=n["case_id"], page=n["page"], pages=npages)
        if not (1 <= meta["evidence"]["page"] <= npages):
            issue("page.out_of_range", pid, where="01_metadata.evidence.page", page=meta["evidence"]["page"], pages=npages)

        # ---- candidate pairs ----
        for p in pairs:
            e, t = claims.get(p["claim_id"]), table_by.get(p["table_id"])
            if e is None:
                issue("ref.pair_claim_missing", pid, pair_id=p["pair_id"], claim_id=p["claim_id"])
            if t is None:
                issue("ref.pair_table_missing", pid, pair_id=p["pair_id"], table_id=p["table_id"])
            claim_text = e["source_text"] if e else ""
            claim_nums = nums(claim_text)
            cell_recs, n_overlap, overlap_tokens = [], 0, set()
            for cid in p["cell_ids"]:
                c = cell_by.get(cid)
                if c is None:
                    issue("ref.pair_cell_missing", pid, pair_id=p["pair_id"], cell_id=cid)
                    continue
                if c["table_id"] != p["table_id"]:
                    issue("ref.pair_cell_in_other_table", pid, pair_id=p["pair_id"], cell_id=cid, cell_table=c["table_id"])
                ov = sorted(set(nums(c["raw_text"])) & set(claim_nums))
                n_overlap += bool(ov)
                overlap_tokens |= set(ov)
                v = c["numeric_value"]
                same_table = [x for x in num_index.get(v, []) if x != cid and x.split("_")[0] == c["table_id"]] if v is not None else []
                other_table = [x for x in num_index.get(v, []) if x.split("_")[0] != c["table_id"]] if v is not None else []
                cell_recs.append({"cell_id": cid, "raw_text": c["raw_text"], "row_label": c["row_label"],
                                  "column_label": c["column_label"], "header_path": c["header_path"],
                                  "numeric_value": v, "uncertainty": c["uncertainty"], "cell_type": c["cell_type"],
                                  "numeric_tokens_shared_with_claim": ov,
                                  "same_numeric_value_elsewhere_same_table": len(same_table),
                                  "same_numeric_value_in_other_tables": len(other_table)})
            head = re.match(r"^\s*(\d+(?:\.\d+)*)\.?\s+[A-Z]", claim_text)
            section_only = bool(overlap_tokens) and head is not None and overlap_tokens <= {head.group(1)}
            all_structural = bool(overlap_tokens) and all(structural_only(tk, claim_text) for tk in overlap_tokens)
            cell_texts = [cell_by[x]["raw_text"] for x in p["cell_ids"] if x in cell_by]
            substring_only = sorted({tk for tk in claim_nums if tk not in overlap_tokens
                                     and any(tk in s for s in cell_texts)}) if not overlap_tokens else []
            if substring_only:
                issue("content.pair_claim_numbers_only_substrings_of_cell_text(heuristic)", pid, pair_id=p["pair_id"],
                      tokens=substring_only, cells=[s[:30] for s in cell_texts[:4]], claim=claim_text[:100])
            if all_structural:
                issue("content.pair_shared_tokens_all_structural_numbers(heuristic)", pid, pair_id=p["pair_id"],
                      tokens=sorted(overlap_tokens), claim=claim_text[:100])
            printed = t["printed_label"] if t else None
            rel_match = norm_label(printed or "") in rel_labels_by_claim.get(p["claim_id"], set())
            if not rel_labels_by_claim.get(p["claim_id"]):
                issue("ref.pair_without_claim_table_relationship", pid, pair_id=p["pair_id"])
            elif not rel_match:
                issue("ref.pair_table_label_not_in_claim_relationships", pid, pair_id=p["pair_id"], printed_label=printed)
            if len(p["cell_ids"]) > 1:
                issue("ambig.pair_references_multiple_cells", pid, pair_id=p["pair_id"], n_cells=len(p["cell_ids"]))
            if n_overlap == 0:
                issue("content.pair_no_numeric_token_overlap(heuristic)", pid, pair_id=p["pair_id"])
            if section_only:
                issue("content.pair_overlap_only_section_number(heuristic)", pid, pair_id=p["pair_id"],
                      tokens=sorted(overlap_tokens), claim=claim_text[:100])
            pair_rows.append({
                "paper_id": pid, "pair_id": p["pair_id"], "claim_id": p["claim_id"], "claim_page": e["page"] if e else None,
                "claim_text": claim_text, "table_id": p["table_id"], "table_printed_label": printed,
                "table_page": t["page"] if t else None, "table_caption": t["caption"][:200] if t else None,
                "table_numeric_fraction": next((r["numeric_fraction"] for r in table_rows
                                                if r["paper_id"] == pid and r["table_id"] == p["table_id"]), None),
                "binding_basis": p["binding_basis"], "confidence": p["confidence"],
                "human_verification_required": p["human_verification_required"],
                "claim_mentions_table_label": label_in_text(printed or "", claim_text),
                "claim_has_relationship_to_same_label": rel_match,
                "claim_numeric_tokens": claim_nums, "n_cells": len(p["cell_ids"]),
                "n_cells_sharing_a_numeric_token_with_claim": n_overlap,
                "shared_tokens": sorted(overlap_tokens), "overlap_is_only_leading_section_number": section_only,
                "shared_tokens_all_structural_numbers": all_structural,
                "claim_numbers_only_as_substrings_of_cell_text": substring_only,
                "cells": cell_recs,
            })

        # ---- declared (audit / INDEX) vs measured ----
        measured = {"tables_detected": len(tables), "cells_extracted": len(cells), "claims_extracted": len(claims),
                    "cross_references": len(xrefs), "claim_table_relationships": len(rels),
                    "candidate_gold_pairs": len(pairs), "numeric_normalization_cases": len(ncases)}
        for k, v in measured.items():
            if audit.get(k) != v:
                issue("count.extraction_audit_vs_measured", pid, field=k, audit=audit.get(k), measured=v)
        ie = idx_by_pid.get(pid)
        if ie is None:
            issue("count.paper_missing_from_INDEX", pid)
        else:
            for ik, mk in (("tables", "tables_detected"), ("cells", "cells_extracted"), ("claims", "claims_extracted"),
                           ("pairs", "candidate_gold_pairs"), ("numeric_normalization_cases", "numeric_normalization_cases")):
                if ie.get(ik) != measured[mk]:
                    issue("count.INDEX_vs_measured", pid, field=ik, index=ie.get(ik), measured=measured[mk])
            if ie.get("source_filename") != d["source_filename"]:
                issue("count.INDEX_source_filename_vs_paper", pid, index=ie.get("source_filename"), paper=d["source_filename"])

        per = {
            "paper_id": pid, "json_filename": fn, "source_filename": d["source_filename"],
            "title": meta["title"], "authors": meta["authors"], "year": meta["year"], "venue": meta["venue"],
            "doi": meta["doi"], "arxiv_id": meta["arxiv_id"], "pages_declared": npages,
            "schema_version": d["schema_version"], "extraction_status": d["extraction_status"],
            "source_of_truth": d["source_of_truth"], "human_verification_required": d["human_verification_required"],
            "tables": len(tables), "table_inventory": len(inv), "cells": len(cells),
            "numeric_cells": sum(c["numeric_value"] is not None for c in cells),
            "claims_unique": len(claims), "claim_evidence_items_10": len(q), "claim_evidence_items_12": len(cc),
            "sections_10_12_identical": sections_identical, "cross_references": len(xrefs),
            "cross_reference_resolution": dict(xref_resolution), "claim_table_relationships": len(rels),
            "claims_with_relationship": len(rel_labels_by_claim), "candidate_pairs": len(pairs),
            "candidate_pair_cell_refs": sum(len(p["cell_ids"]) for p in pairs),
            "numeric_normalization_cases": len(ncases),
            "section_status": {s: d[s]["status"] for s in SECTIONS},
            "section_evidence_items": {s: len(d[s]["evidence"]) for s in SECTIONS},
            "extraction_audit": audit, "index_entry": ie,
        }
        papers.append(per)
        for k in ("tables", "table_inventory", "cells", "numeric_cells", "claims_unique", "cross_references",
                  "claim_table_relationships", "claims_with_relationship", "candidate_pairs",
                  "candidate_pair_cell_refs", "numeric_normalization_cases"):
            totals[k] += per[k]
        totals["papers_with_candidate_pairs"] += bool(pairs)
        totals["papers_with_relationships"] += bool(rels)
        totals["papers_with_numeric_cases"] += bool(ncases)

    unique_pair_cells = {(r["paper_id"], c["cell_id"]) for r in pair_rows for c in r["cells"]}
    totals["candidate_pair_unique_cells"] = len(unique_pair_cells)
    totals["candidate_pairs_single_cell"] = sum(r["n_cells"] == 1 for r in pair_rows)
    dist["pair.n_cells"] = Counter(r["n_cells"] for r in pair_rows)
    idx_tot = index.get("totals", {})
    declared_vs_measured = {
        k: {"INDEX_totals": idx_tot.get(ik), "measured": totals[mk], "match": idx_tot.get(ik) == totals[mk]}
        for k, ik, mk in (("tables", "tables", "tables"), ("cells", "cells", "cells"), ("claims", "claims", "claims_unique"),
                          ("pairs", "pairs", "candidate_pairs"),
                          ("numeric_normalization_cases", "numeric_normalization_cases", "numeric_normalization_cases"))}
    declared_vs_measured["paper_count"] = {"INDEX_totals": index.get("paper_count"), "measured": len(paper_files),
                                           "match": index.get("paper_count") == len(paper_files)}

    checks = {}
    for name in sorted(ISSUES):
        recs = ISSUES[name]
        checks[name] = {"count": len(recs), "n_papers": len({r["paper_id"] for r in recs}),
                        "papers": sorted({r["paper_id"] for r in recs}), "examples": recs[:MAX_EXAMPLES]}

    inventory = {
        "artifact": "candidate_gold_inventory",
        "dataset_status": "CANDIDATE -- not verified gold. Nothing here is verified against the physical PDFs.",
        "provenance": {
            "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "script": str(Path(__file__).resolve().relative_to(ROOT)).replace("\\", "/"),
            "python": sys.version.split()[0], "platform": platform.platform(),
            "git_head": git("rev-parse", "HEAD"), "git_branch": git("rev-parse", "--abbrev-ref", "HEAD"),
            "git_status_porcelain": git("status", "--porcelain").splitlines(),
        },
        "zip": {"path": str(ZIP.relative_to(ROOT)).replace("\\", "/"), "size_bytes": len(raw_zip),
                "sha256": sha256(raw_zip), "testzip_first_bad_member": zf.testzip(),
                "n_members": len(members), "members": members,
                "paper_member_numbering_contiguous": paper_files == expected,
                "unexpected_members": unexpected},
        "readme_txt": readme,
        "index_json": {"schema_version": index.get("schema_version"), "status": index.get("status"),
                       "human_verification_required": index.get("human_verification_required"),
                       "paper_count": index.get("paper_count"), "totals": idx_tot},
        "ids": {"paper_ids": [p["paper_id"] for p in papers], "json_filenames": paper_files,
                "source_filenames": [p["source_filename"] for p in papers],
                "schema_versions": sorted({p["schema_version"] for p in papers})},
        "measured_totals": dict(totals),
        "declared_vs_measured": declared_vs_measured,
        "distributions": {k: {str(kk): vv for kk, vv in sorted(v.items(), key=lambda kv: -kv[1])} for k, v in dist.items()},
        "integrity_checks": checks,
        "papers": papers,
        "tables": table_rows,
        "candidate_pairs": pair_rows,
        "schema": {"paths": {p: {"types": dict(types[p]), "n_papers": len(present[p])} for p in sorted(types)},
                   "type_variants": type_variants},
        "pdf_presence_preliminary": pdf_presence([p["source_filename"] for p in papers]),
    }
    OUT.write_text(json.dumps(inventory, indent=1, ensure_ascii=False), encoding="utf-8")

    # compact console summary
    print(f"wrote {OUT.relative_to(ROOT)}")
    print("zip sha256", inventory["zip"]["sha256"], "| testzip:", inventory["zip"]["testzip_first_bad_member"],
          "| members:", len(members), "| json parse failures:", len(ISSUES.get("json.syntax_error", [])))
    print("measured_totals", dict(totals))
    print("declared_vs_measured", {k: v["match"] for k, v in declared_vs_measured.items()})
    for name, c in checks.items():
        print(f"  {c['count']:>6}  papers={c['n_papers']:>2}  {name}")
    hits = inventory["pdf_presence_preliminary"]["hits"]
    print("pdf present:", sum(bool(v) for v in hits.values()), "/", len(hits))


if __name__ == "__main__":
    main()
