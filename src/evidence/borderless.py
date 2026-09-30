"""Borderless PDF tables (phase 09A): Docling + Table Transformer consensus behind `borderless_policy`.

Only caption blocks the ruled path left as `no_ruled_table_beside_caption` come here. The routing and
the flag are in represent.py (`_attach_borderless_cells`, `_borderless_policy`). The heavy dependencies
(docling, transformers, timm, torch: requirements-borderless.txt) are imported inside the adapters, so
importing this module costs nothing while the policy is `off`.

Per table, both parsers must find a table beside the caption (the ruled path's gap rule) and pass three
gates:
  G1  text-layer fidelity: every numeric cell value is a contiguous run of text-layer words inside the
      table bbox, compared after `norm`;
  G2  coverage: every digit-bearing word in the bbox (caption/footnote lines excluded) is covered by
      exactly one grid text;
  G3  structure: header <= 40 chars, row label <= 60 chars, >= 2 data rows, >= 2 columns, no newline in
      a header.
They must also agree on every numeric (row label, column header, value) triple.
  Parser A: Docling, TableFormer ACCURATE, do_cell_matching (text comes from the PDF text layer).
  Parser B: Table Transformer detection + structure v1.1-all on a 150-dpi render; cell text comes from
            PyMuPDF words. No OCR.

Otherwise the table stays pdf_only and `borderless_rejected:{no_candidate|G1|G2|G3|disagree}` is appended
to its `table_fallback`. A crash appends `borderless_error:<exception>`, never a silent rejection. An
accepted table carries parser A's numeric cells in the ruled path's table_cell schema.
Definitions: src/evaluation/borderless_09a/PREREG_09A.md (O3-O11).
"""
from __future__ import annotations

import re
import time
from collections import Counter, defaultdict
from typing import Any

from .represent import _PDF_CAPTION_GAP, _PDF_MIN_OVERLAP, _pdf_grid_cells, _pdf_row_label_column, _ws

TATR_DPI = 150
TATR_DET_MODEL = "microsoft/table-transformer-detection"
TATR_STR_MODEL = "microsoft/table-transformer-structure-recognition-v1.1-all"
TATR_DET_THRESHOLD = 0.9
TATR_STR_THRESHOLD = 0.5
TATR_PAD_PX = 10
TATR_STR_LONGEST_EDGE = 800      # the v1.1-all preprocessor config's size, applied here (see parser_b_tables)
MAX_RUN_WORDS = 12
G3_MAX_HEADER = 40
G3_MAX_ROW_LABEL = 60
BACKENDS = {"A": "docling:TableFormer-ACCURATE+cell_matching",
            "B": f"tatr:detection+structure-v1.1-all@{TATR_DPI}dpi"}
_DIGIT = re.compile(r"\d")
_SPACE = re.compile(r"[\s  -​ ]+")
_TRAILING_MARKS = re.compile(r"[*†‡§¶]+$")
_FOOTNOTE_FIRST = re.compile(r"^(?:table|tab|fig|figure|note|notes|abbreviations?|\*|†|‡|§|¶)$", re.I)


# --- normalisation and the text layer ------------------------------------------------------------------------
def _core(s: Any) -> str:
    return _SPACE.sub("", str(s or "").replace("−", "-").replace("**", "").replace("__", ""))


def norm(s: Any) -> str:
    """O7: U+2212 minus -> '-', bold/italic markup and trailing * † ‡ § ¶ markers dropped, all whitespace
    (including nbsp and thin spaces) removed, casefolded. So '0.87±0.06' == '0.87 ± 0.06'."""
    return _TRAILING_MARKS.sub("", _core(s)).casefold()


def page_words(page) -> list[tuple]:
    """PyMuPDF words (x0, y0, x1, y1, text, block, line, word) in native text-layer order."""
    return sorted(page.get_text("words"), key=lambda w: (w[5], w[6], w[7]))


def words_in(words: list[tuple], bbox, tol: float = 0.5) -> list[tuple]:
    x0, y0, x1, y1 = bbox
    return [w for w in words if x0 - tol <= (w[0] + w[2]) / 2 <= x1 + tol and y0 - tol <= (w[1] + w[3]) / 2 <= y1 + tol]


def find_runs(words: list[tuple], text: Any) -> list[tuple[int, int]]:
    """Spans [i, j) of consecutive words (at most MAX_RUN_WORDS) whose joined text normalises to norm(text)."""
    target = norm(text)
    if not target:
        return []
    out = []
    for i in range(len(words)):
        raw = ""
        for j in range(i, min(len(words), i + MAX_RUN_WORDS)):
            raw = f"{raw} {words[j][4]}" if raw else words[j][4]
            if norm(raw) == target:
                out.append((i, j + 1))
                break
            if len(_core(raw)) > len(target) + 4:
                break
    return out


# --- grid, gates, consensus ---------------------------------------------------------------------------------------
def grid_of(t: dict) -> tuple[list[str], list[list[str | None]], list[dict]]:
    """(header, body, digit-bearing cells) of a parser table {bbox, rows, cols, cells: [{r0, r1, c0, c1, text,
    header, center}]}. O6:
    - header rows are the leading rows covered by a column-header cell (none -> row 0);
    - several header rows fold per column into 'top / sub';
    - a spanning cell's text sits at its top-left position, and the positions it covers are None
      (the ruled path's carry-down convention)."""
    n_r, n_c = t["rows"], t["cols"]
    cover: dict[tuple[int, int], dict] = {}
    for c in t["cells"]:
        for r in range(c["r0"], max(c["r1"], c["r0"] + 1)):
            for k in range(c["c0"], max(c["c1"], c["c0"] + 1)):
                if 0 <= r < n_r and 0 <= k < n_c:
                    cover.setdefault((r, k), c)
    n_hdr = 0
    while n_hdr < n_r and any((cover.get((n_hdr, k)) or {}).get("header") for k in range(n_c)):
        n_hdr += 1
    n_hdr = n_hdr or 1
    header = []
    for k in range(n_c):
        levels: list[str] = []
        for r in range(min(n_hdr, n_r)):
            txt = _ws(cover[(r, k)]["text"]) if (r, k) in cover else ""
            if txt and (not levels or levels[-1] != txt):
                levels.append(txt)
        header.append(" / ".join(levels))
    body = []
    for r in range(n_hdr, n_r):
        row: list[str | None] = []
        for k in range(n_c):
            c = cover.get((r, k))
            row.append("" if c is None else (str(c["text"] or "").strip() if (c["r0"], c["c0"]) == (r, k) else None))
        body.append(row)
    return header, body, [c for c in t["cells"] if _DIGIT.search(str(c["text"] or ""))]


def gate_g1(body: list[list[str | None]], lab: int, words: list[tuple]) -> dict:
    fails = [v for row in body for k, v in enumerate(row) if k != lab and v and _DIGIT.search(v) and not find_runs(words, v)]
    return {"pass": not fails, "failures": fails[:20], "n_failures": len(fails)}


def gate_g2(texts: list[dict], words: list[tuple], caption_bbox) -> dict:
    lines: dict[tuple, list[int]] = defaultdict(list)
    for i, w in enumerate(words):
        lines[(w[5], w[6])].append(i)
    excluded: set[int] = set()
    for idx in lines.values():
        first = words[min(idx, key=lambda i: words[i][7])][4].strip().rstrip(":.")
        in_caption = caption_bbox is not None and any(
            caption_bbox[0] <= (words[i][0] + words[i][2]) / 2 <= caption_bbox[2]
            and caption_bbox[1] <= (words[i][1] + words[i][3]) / 2 <= caption_bbox[3] for i in idx)
        if in_caption or _FOOTNOTE_FIRST.match(first):
            excluded.update(idx)
    digit_words = [i for i, w in enumerate(words) if _DIGIT.search(w[4]) and i not in excluded]
    cover: Counter = Counter()
    unmatched = []
    for t in texts:
        runs = find_runs(words, t["text"])
        if not runs:
            unmatched.append(_ws(t["text"]))
            continue
        run = runs[0]
        if t.get("center"):
            cx, cy = t["center"]

            def dist(r: tuple[int, int]) -> float:
                ws_ = words[r[0]:r[1]]
                mx = sum((w[0] + w[2]) / 2 for w in ws_) / len(ws_)
                my = sum((w[1] + w[3]) / 2 for w in ws_) / len(ws_)
                return (mx - cx) ** 2 + (my - cy) ** 2
            run = min(runs, key=dist)
        for i in range(*run):
            cover[i] += 1
    missing = [words[i][4] for i in digit_words if cover[i] == 0]
    dup = [words[i][4] for i in digit_words if cover[i] > 1]
    return {"pass": not missing and not dup, "digit_words": len(digit_words), "n_missing": len(missing),
            "missing": missing[:20], "n_duplicated": len(dup), "duplicated": dup[:20], "unmatched_texts": unmatched[:20]}


def gate_g3(header: list[str], body: list[list[str | None]], lab: int) -> dict:
    problem = None
    if len(header) < 2:
        problem = f"too_few_columns:{len(header)}"
    elif len(body) < 2:
        problem = f"too_few_data_rows:{len(body)}"
    elif any("\n" in h for h in header):
        problem = "newline_in_header"
    elif any(len(h) > G3_MAX_HEADER for h in header):
        problem = "header_too_long"
    elif any(len(_ws(r[lab] or "")) > G3_MAX_ROW_LABEL for r in body):
        problem = "row_label_too_long"
    return {"pass": problem is None, "problem": problem}


def match_caption(tables: list[dict], cap) -> tuple[dict, float] | None:
    """O5: the ruled path's caption<->table gap rule, applied to a parser's table bboxes."""
    best = None
    for t in tables:
        x0, y0, x1, y1 = t["bbox"]
        if y0 >= cap[3] - 3:
            gap = max(0.0, y0 - cap[3])                  # table below its caption
        elif cap[1] <= y0 < cap[3]:
            gap = 0.0                                    # caption block runs into the table top
        elif y1 <= cap[1] + 3:
            gap = max(0.0, cap[1] - y1) + 0.5            # table above its caption
        else:
            continue
        if gap <= _PDF_CAPTION_GAP and min(cap[2], x1) - max(cap[0], x0) >= _PDF_MIN_OVERLAP * min(cap[2] - cap[0], x1 - x0):
            if best is None or gap < best[1]:
                best = (t, gap)
    return best


def evaluate_candidate(tables: list[dict], cap, words: list[tuple], caption: str, section: str | None, pno: int) -> dict:
    m = match_caption(tables, cap)
    if m is None:
        return {"candidate": False, "n_tables_on_page": len(tables)}
    t, gap = m
    header, body, texts = grid_of(t)
    bw = words_in(words, t["bbox"])
    shaped = bool(header) and bool(body)
    lab, rule = _pdf_row_label_column(header, body) if shaped else (0, None)
    cells = [c for c in (_pdf_grid_cells(header, body, caption, section, pno)[0] if shaped else []) if _DIGIT.search(c["value"])]
    everything = [_ws(x) for row in body for x in row if x] + header
    return {"candidate": True, "n_tables_on_page": len(tables), "bbox": [round(v, 1) for v in t["bbox"]],
            "gap": round(gap, 1), "shape": [len(body), len(header)], "header": header, "label_col": lab, "rule": rule,
            "G1": gate_g1(body, lab, bw), "G2": gate_g2(texts, bw, cap), "G3": gate_g3(header, body, lab),
            "cells": cells, "triples": sorted([norm(c["row_label"]), norm(c["column_header"]), norm(c["value"])] for c in cells),
            "absorbed_text": [x for x in everything if len(x) > 60 or len(x.split()) >= 8][:10]}


def decide(a: dict, b: dict) -> tuple[str | None, list, list]:
    """The first failing code in the pre-registered order no_candidate -> G1 -> G2 -> G3 -> disagree, or None
    (accepted). Also returns the triples only A has and only B has."""
    if not a.get("candidate") or not b.get("candidate"):
        return "no_candidate", [], []
    ta, tb = Counter(map(tuple, a["triples"])), Counter(map(tuple, b["triples"]))
    only_a, only_b = sorted(map(list, (ta - tb).elements())), sorted(map(list, (tb - ta).elements()))
    for g in ("G1", "G2", "G3"):
        if not (a[g]["pass"] and b[g]["pass"]):
            return g, only_a, only_b
    return (None if ta == tb else "disagree"), only_a, only_b


# --- parser A: Docling -----------------------------------------------------------------------------------------
_DOCLING = None


def _docling():
    global _DOCLING
    if _DOCLING is None:
        from docling.datamodel.accelerator_options import AcceleratorDevice, AcceleratorOptions
        from docling.datamodel.base_models import InputFormat
        from docling.datamodel.pipeline_options import PdfPipelineOptions, TableFormerMode
        from docling.document_converter import DocumentConverter, PdfFormatOption
        opts = PdfPipelineOptions()
        opts.do_ocr = False
        opts.do_table_structure = True
        opts.table_structure_options.mode = TableFormerMode.ACCURATE
        opts.table_structure_options.do_cell_matching = True
        opts.accelerator_options = AcceleratorOptions(device=AcceleratorDevice.CPU)
        _DOCLING = DocumentConverter(format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=opts)})
    return _DOCLING


def parser_a_tables(data: bytes, pno: int) -> list[dict]:
    """Docling tables on page `pno` (1-based), each as {bbox (top-left PDF points), rows, cols, cells}."""
    from io import BytesIO
    from docling.datamodel.base_models import DocumentStream
    doc = _docling().convert(DocumentStream(name="paper.pdf", stream=BytesIO(data)), page_range=(pno, pno)).document
    out = []
    for t in doc.tables:
        prov = [p for p in t.prov if p.page_no == pno]
        if not prov:
            continue
        h = doc.pages[pno].size.height
        bb = prov[0].bbox.to_top_left_origin(page_height=h)
        cells = []
        for c in t.data.table_cells:
            center = None
            if c.bbox is not None:
                cb = c.bbox.to_top_left_origin(page_height=h)
                center = ((cb.l + cb.r) / 2, (cb.t + cb.b) / 2)
            cells.append({"r0": c.start_row_offset_idx, "r1": c.end_row_offset_idx, "c0": c.start_col_offset_idx,
                          "c1": c.end_col_offset_idx, "text": c.text, "header": bool(c.column_header), "center": center})
        out.append({"bbox": [bb.l, bb.t, bb.r, bb.b], "rows": t.data.num_rows, "cols": t.data.num_cols, "cells": cells})
    return out


# --- parser B: Table Transformer -----------------------------------------------------------------------------------
_TATR = None


def _tatr_model(repo: str):
    """Compatibility shim 1: the v1.1-all config ships `"dilation": null`. transformers 5 rejects null for
    this bool field; transformers 4 read it as False (no dilation). Setting False is the same model."""
    from transformers import TableTransformerConfig, TableTransformerForObjectDetection
    cfg, _ = TableTransformerConfig.get_config_dict(repo)
    if "dilation" in cfg and cfg["dilation"] is None:
        cfg["dilation"] = False
    return TableTransformerForObjectDetection.from_pretrained(repo, config=TableTransformerConfig.from_dict(cfg)).eval()


def _tatr():
    global _TATR
    if _TATR is None:
        import torch
        from transformers import AutoImageProcessor
        _TATR = (torch, AutoImageProcessor.from_pretrained(TATR_DET_MODEL), _tatr_model(TATR_DET_MODEL),
                 AutoImageProcessor.from_pretrained(TATR_STR_MODEL), _tatr_model(TATR_STR_MODEL))
    return _TATR


def _objects(proc, model, image, threshold: float, target_hw: tuple[int, int], **kw) -> list[tuple[str, float, list[float]]]:
    torch = _tatr()[0]
    inputs = proc(images=image, return_tensors="pt", **kw)
    with torch.no_grad():
        out = model(**inputs)
    res = proc.post_process_object_detection(out, threshold=threshold, target_sizes=[target_hw])[0]
    return [(model.config.id2label[int(lab)], float(s), [float(v) for v in b])
            for s, lab, b in zip(res["scores"], res["labels"], res["boxes"])]


def _dedupe(boxes: list[list[float]], axis: int) -> list[list[float]]:
    lo, hi = (1, 3) if axis == 1 else (0, 2)
    kept: list[list[float]] = []
    for b in boxes:
        if kept and min(kept[-1][hi], b[hi]) - max(kept[-1][lo], b[lo]) > 0.5 * min(kept[-1][hi] - kept[-1][lo], b[hi] - b[lo]):
            continue
        kept.append(b)
    return kept


def _tatr_cells(rows, cols, heads, spans, words) -> dict:
    """row ∩ column cells, spanning cells merged, each word assigned to the row and the column of largest
    overlap (or to the spanning cell containing its centre)."""
    def ov(a0, a1, b0, b1):
        return max(0.0, min(a1, b1) - max(a0, b0))
    hdr = {r for r, rb in enumerate(rows) if any(h[1] <= (rb[1] + rb[3]) / 2 <= h[3] for h in heads)}
    span_cells, covered = [], {}
    for s in spans:
        rs = [r for r, rb in enumerate(rows) if s[1] <= (rb[1] + rb[3]) / 2 <= s[3]]
        cs = [c for c, cb in enumerate(cols) if s[0] <= (cb[0] + cb[2]) / 2 <= s[2]]
        if len(rs) * len(cs) < 2 or any((r, c) in covered for r in rs for c in cs):
            continue
        cell = {"r0": min(rs), "r1": max(rs) + 1, "c0": min(cs), "c1": max(cs) + 1, "header": min(rs) in hdr,
                "words": [], "box": s}
        span_cells.append(cell)
        covered.update({(r, c): cell for r in rs for c in cs})
    grid = {(r, c): {"r0": r, "r1": r + 1, "c0": c, "c1": c + 1, "header": r in hdr, "words": [],
                     "box": [cols[c][0], rows[r][1], cols[c][2], rows[r][3]]}
            for r in range(len(rows)) for c in range(len(cols)) if (r, c) not in covered}
    for w in words:
        cx, cy = (w[0] + w[2]) / 2, (w[1] + w[3]) / 2
        cell = next((sc for sc in span_cells if sc["box"][0] <= cx <= sc["box"][2] and sc["box"][1] <= cy <= sc["box"][3]), None)
        if cell is None:
            if not rows or not cols:
                continue
            rv = [ov(w[1], w[3], rb[1], rb[3]) for rb in rows]
            cv = [ov(w[0], w[2], cb[0], cb[2]) for cb in cols]
            if max(rv) <= 0 or max(cv) <= 0:
                continue
            key = (rv.index(max(rv)), cv.index(max(cv)))
            cell = covered.get(key) or grid[key]
        cell["words"].append(w)
    cells = []
    for cell in span_cells + list(grid.values()):
        ws_ = sorted(cell.pop("words"), key=lambda w: (w[5], w[6], w[7]))
        box = cell.pop("box")
        cells.append({**cell, "text": " ".join(w[4] for w in ws_), "center": ((box[0] + box[2]) / 2, (box[1] + box[3]) / 2)})
    return {"rows": len(rows), "cols": len(cols), "cells": cells}


def parser_b_tables(page, words: list[tuple]) -> list[dict]:
    """Table Transformer tables on `page`: detection on a TATR_DPI render, then structure recognition on each
    detected table's crop.
    Compatibility shim 2: the v1.1-all preprocessor config gives only longest_edge=800, which transformers
    5's DetrImageProcessor rejects. The crop is therefore resized here to that longest edge (aspect kept)
    and the processor is called with do_resize=False."""
    from PIL import Image
    _, det_p, det_m, str_p, str_m = _tatr()
    pix = page.get_pixmap(dpi=TATR_DPI)
    img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    k = 72.0 / TATR_DPI
    out = []
    for label, score, (x0, y0, x1, y1) in _objects(det_p, det_m, img, TATR_DET_THRESHOLD, (img.height, img.width)):
        if label != "table":
            continue
        ox, oy = max(0.0, x0 - TATR_PAD_PX), max(0.0, y0 - TATR_PAD_PX)
        crop = img.crop((ox, oy, min(img.width, x1 + TATR_PAD_PX), min(img.height, y1 + TATR_PAD_PX)))
        f = TATR_STR_LONGEST_EDGE / max(crop.size)
        small = crop.resize((max(1, round(crop.width * f)), max(1, round(crop.height * f))), Image.BILINEAR)
        objs = _objects(str_p, str_m, small, TATR_STR_THRESHOLD, (crop.height, crop.width), do_resize=False)

        def pt(b):
            return [(b[0] + ox) * k, (b[1] + oy) * k, (b[2] + ox) * k, (b[3] + oy) * k]
        rows = _dedupe(sorted((pt(b) for lab, _, b in objs if lab == "table row"), key=lambda b: b[1] + b[3]), 1)
        cols = _dedupe(sorted((pt(b) for lab, _, b in objs if lab == "table column"), key=lambda b: b[0] + b[2]), 0)
        heads = [pt(b) for lab, _, b in objs if lab == "table column header"]
        spans = [pt(b) for lab, _, b in objs if lab == "table spanning cell"]
        bbox = [x0 * k, y0 * k, x1 * k, y1 * k]
        out.append({"bbox": bbox, "score": round(score, 3), **_tatr_cells(rows, cols, heads, spans, words_in(words, bbox))})
    return out


# --- entry point (called by represent._attach_borderless_cells) ----------------------------------------------
def attach_borderless(data: bytes, doc, todo: list[tuple[dict, int, tuple]]) -> None:
    """Decide every routed caption block in place. Each parser runs once per page; the seconds are per page,
    shared by that page's captions."""
    by_page: dict[int, list] = defaultdict(list)
    for b, pno, bbox in todo:
        by_page[pno].append((b, [float(v) for v in bbox]))
    for pno, caps in sorted(by_page.items()):
        page = doc[pno - 1]
        words = page_words(page)
        runs = {}
        for key, fn in (("A", lambda: parser_a_tables(data, pno)), ("B", lambda: parser_b_tables(page, words))):
            t0 = time.perf_counter()
            try:
                runs[key] = {"tables": fn(), "error": None}
            except Exception as e:  # noqa: BLE001 -- recorded as borderless_error, never a silent rejection
                runs[key] = {"tables": None, "error": f"{type(e).__name__}: {e}"}
            runs[key]["seconds"] = round(time.perf_counter() - t0, 2)
        for b, cap in caps:
            _decide_block(b, pno, cap, words, runs, len(caps))


def _decide_block(b: dict, pno: int, cap, words: list[tuple], runs: dict, n_caps: int) -> None:
    caption = _ws(b["text"])[:400]
    parsers = {}
    for key in ("A", "B"):
        r = runs[key]
        d = {"backend": BACKENDS[key], "seconds_page": r["seconds"], "captions_on_page": n_caps, "error": r["error"]}
        if r["error"] is None:
            d.update(evaluate_candidate(r["tables"], cap, words, caption, b.get("section"), pno))
        parsers[key] = d
    detail = {"policy": "consensus", "page": pno, "caption_bbox": [round(v, 1) for v in cap], "parsers": parsers}
    errors = [f"{k}: {p['error']}" for k, p in parsers.items() if p["error"]]
    if errors:
        detail.update(verdict="error", code=None, error="; ".join(errors))
        b.update(table_fallback=f"{b['table_fallback']}; borderless_error:{detail['error']}", table_borderless=detail)
        return
    code, only_a, only_b = decide(parsers["A"], parsers["B"])
    detail.update(verdict="accepted" if code is None else "rejected", code=code, error=None,
                  agree=(parsers["A"].get("candidate") and parsers["B"].get("candidate") and not only_a and not only_b) or False,
                  triples_only_in_A=only_a[:20], triples_only_in_B=only_b[:20])
    if code is None:
        a = parsers["A"]
        b.update(table_cells=a["cells"], table_caption=caption, table_parse_status="parsed", table_fallback=None,
                 table_backend="borderless:consensus", table_bbox=a["bbox"], table_row_label_rule=a["rule"],
                 table_shape=a["shape"], table_borderless=detail)
    else:
        b.update(table_fallback=f"{b['table_fallback']}; borderless_rejected:{code}", table_borderless=detail)
