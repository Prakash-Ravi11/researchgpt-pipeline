"""Inventory every native PDF page using the installed PyMuPDF adapter.

No retrieval ranking or numeric-value deduplication enters discovery.
"""
from __future__ import annotations
import hashlib
import re
from . import SOURCE_VERSION
from .contracts import identity
from .measurements import NUMBER
from src.evidence.prose_attribution.source import normalize_with_map

NUMERIC = re.compile(r"(?<![\w.])" + NUMBER + r"(?:\s*%)?")
OUTCOME = re.compile(r"\b(?:improv\w*|reduc\w*|increas\w*|decreas\w*|outperform\w*|"
                     r"fail\w*|achiev\w*|demonstrat\w*|observ\w*|no significant|comparable)\b", re.I)

def _inside(box, token):
    x, y = (token["bbox"][0] + token["bbox"][2])/2, (token["bbox"][1] + token["bbox"][3])/2
    return box[0] <= x <= box[2] and box[1] <= y <= box[3]

def inventory_pdf(path, paper_id):
    import pymupdf
    data = path.read_bytes() if hasattr(path, "read_bytes") else __import__("pathlib").Path(path).read_bytes()
    source_hash = hashlib.sha256(data).hexdigest()
    parser = {"name": "pymupdf", "version": pymupdf.VersionBind, "tables": "lines",
              "source_contract": SOURCE_VERSION}
    representation = identity({"source": source_hash, "parser": parser})
    prefix = paper_id + ":" + representation[:20]
    units, pages, tables, tokens, candidates = [], [], [], [], []
    def unit(local, raw, page, bbox, kind, token_ids=(), **extra):
        normalized, offsets = normalize_with_map(raw)
        row = {"id": prefix + ":" + local, "paper_id": paper_id, "source_sha256": source_hash,
               "representation_id": representation, "type": kind, "raw_text": raw,
               "normalized_text": normalized, "normalization_map": offsets,
               "page": page, "bbox": bbox, "coordinate_system": "pdf_points_top_left_y_down",
               "token_ids": list(token_ids), "provenance": "native", **extra}
        units.append(row)
        return row
    with pymupdf.open(stream=data, filetype="pdf") as pdf:
        for pno, page in enumerate(pdf, 1):
            words = page.get_text("words")
            ptokens = [{"id": prefix + f":p{pno}:w{i}", "text": w[4], "bbox": list(w[:4]),
                        "page": pno, "block": w[5], "line": w[6], "word": w[7]}
                       for i, w in enumerate(words)]
            tokens.extend(ptokens)
            blocks = page.get_text("blocks")
            text = page.get_text()
            pages.append({"page": pno, "width": page.rect.width, "height": page.rect.height,
                          "status": "inventoried" if text.strip() else "needs_ocr",
                          "reason": None if text.strip() else "no_native_text_visual_repair_required",
                          "native_text_sha256": hashlib.sha256(text.encode()).hexdigest()})
            table_boxes = []
            try:
                detected = page.find_tables().tables
            except Exception as exc:
                detected = []
                pages[-1]["table_status"] = "unresolved"
                pages[-1]["table_error"] = type(exc).__name__
            for image_index,image in enumerate(page.get_image_info(hashes=True)):
                image_unit=unit(f"p{pno}:image{image_index}","",pno,list(image["bbox"]),"image",
                    image_digest=image["digest"].hex(),image_digest_algorithm="md5",
                    width=image["width"],height=image["height"],visual_status="unresolved")
                candidates.append({"id":image_unit["id"]+":visual","unit_id":image_unit["id"],
                    "kind":"visual","raw_text":"","start":0,"end":0,"table_id":None,
                    "reason":"visual_content_not_interpreted"})
            for ti, table in enumerate(detected):
                table_id = prefix + f":p{pno}:t{ti}"
                grid = table.extract()
                rects = [box for row in table.rows for box in row.cells if box]
                xs = sorted(set(round(x, 3) for box in rects for x in (box[0], box[2])))
                ys = sorted(set(round(y, 3) for box in rects for y in (box[1], box[3])))
                cells = []
                for row_index, row in enumerate(table.rows):
                    for col, box in enumerate(row.cells):
                        if box is None:
                            continue
                        raw = grid[row_index][col] or ""
                        members = [t["id"] for t in ptokens if _inside(box, t)]
                        cell = unit(f"p{pno}:t{ti}:r{row_index}:c{col}", raw, pno, list(box),
                            "table_cell", members, table_id=table_id, row=row_index, col=col,
                            row_span=max(1, sum(box[1] <= y < box[3] - .01 for y in ys)),
                            col_span=max(1, sum(box[0] <= x < box[2] - .01 for x in xs)),
                            cell_state="value" if raw else "blank")
                        cells.append(cell)
                def adjacent_caption(b):
                    overlap=max(0,min(b[2],table.bbox[2])-max(b[0],table.bbox[0]))
                    horizontal=overlap/max(1,min(b[2]-b[0],table.bbox[2]-table.bbox[0]))
                    return horizontal>=.5 and ((b[3]<=table.bbox[1] and table.bbox[1]-b[3]<=100)
                        or (b[1]>=table.bbox[3] and b[1]-table.bbox[3]<=70))
                nearby=[b for b in blocks if adjacent_caption(b) and re.match(r"\s*Table\s+\d+",b[4],re.I)]
                caption=nearby[0] if len(nearby)==1 else None
                cap = unit(f"p{pno}:t{ti}:caption", caption[4] if caption else "", pno,
                           list(caption[:4]) if caption else None, "caption")
                notes = [unit(f"p{pno}:t{ti}:note{ni}", b[4], pno, list(b[:4]), "footnote")
                         for ni, b in enumerate(blocks)
                         if 0 <= b[1] - table.bbox[3] < 65 and
                         re.match(r"\s*(?:Note\b|[*\u2020\u2021])", b[4], re.I)]
                owners = {}
                for cell in cells:
                    for token in cell["token_ids"]:
                        owners.setdefault(token, []).append(cell["id"])
                overlap = [token for token, own in owners.items() if len(own) != 1]
                signature = [c["raw_text"] for c in cells if c["row"] == 0]
                continued = None
                if re.search(r"continu", cap["raw_text"], re.I):
                    label = re.match(r"\s*Table\s+(\d+)", cap["raw_text"], re.I)
                    for prev in reversed(tables):
                        previous_label = re.match(r"\s*Table\s+(\d+)", prev["caption"], re.I)
                        if label and previous_label and label[1] == previous_label[1] and prev["header_signature"] == signature:
                            continued = prev["id"]; break
                slots=[]
                for ri, gridrow in enumerate(table.rows):
                    slotrow=[]
                    for ci, box in enumerate(gridrow.cells):
                        direct=next((c for c in cells if c["row"]==ri and c["col"]==ci),None)
                        owner=direct or next((c for c in cells if c["row"]<=ri<c["row"]+c["row_span"]
                                              and c["col"]<=ci<c["col"]+c["col_span"]),None)
                        slotrow.append({"state":direct["cell_state"] if direct else "covered" if owner else "missing_structure",
                                        "owner_id":owner["id"] if owner else None})
                    slots.append(slotrow)
                tables.append({"grid_slot_states":slots, "id": table_id, "source_sha256": source_hash, "representation_id": representation,
                    "page": pno, "bbox": list(table.bbox), "caption": cap["raw_text"],
                    "caption_id": cap["id"], "cell_ids": [c["id"] for c in cells],
                    "rows": table.row_count, "cols": table.col_count, "header_signature": signature,
                    "grid_slots": [[None if box is None else next(c["id"] for c in cells
                         if c["row"] == ri and c["col"] == ci) for ci, box in enumerate(row.cells)]
                         for ri, row in enumerate(table.rows)],
                    "notes": [n["id"] for n in notes], "continuation_of": continued,
                    "token_assignment_conflicts": overlap, "status": "unresolved" if overlap else "inventoried"})
                table_boxes.append(list(table.bbox))
            page_cell_ids = {cid for tab in tables if tab["page"] == pno for cid in tab["cell_ids"]}
            claimed = {token for cell in units if cell["id"] in page_cell_ids for token in cell["token_ids"]}
            for bi, block in enumerate(blocks):
                if block[6] != 0:
                    continue
                members = [t["id"] for t in ptokens if t["block"] == block[5]]
                u = unit(f"p{pno}:b{bi}", block[4], pno, list(block[:4]), "paragraph", members)
                # Table text remains in the inventory; cell-owned tokens do not become duplicate candidates.
                u["table_token_ids"] = [t for t in members if t in claimed]
                cursor=0;u["word_char_spans"]=[]
                for token in ptokens:
                    if token["id"] not in members:continue
                    offset=u["raw_text"].find(token["text"],cursor)
                    if offset>=0:
                        u["word_char_spans"].append({"start":offset,"end":offset+len(token["text"]),"token_id":token["id"]})
                        cursor=offset+len(token["text"])

    for u in units:
        if u["type"] not in {"paragraph", "table_cell"}:
            continue
        if u["type"] == "paragraph" and u["token_ids"] and len(u["table_token_ids"]) == len(u["token_ids"]):
            continue
        matches = list(NUMERIC.finditer(u["raw_text"]))
        for match in matches:
            source_words=[w for w in u.get("word_char_spans",[]) if w["start"]<match.end() and w["end"]>match.start()]
            if source_words and all(w["token_id"] in u.get("table_token_ids",[]) for w in source_words):
                continue
            candidates.append({"id": u["id"] + f":n{match.start()}", "unit_id": u["id"],
                "kind": "numeric", "raw_text": match.group(), "start": match.start(), "end": match.end(),
                "table_id": u.get("table_id"), "state": "unresolved"})
        if u["type"] == "paragraph":
            candidates.append({"id": u["id"] + ":qualitative", "unit_id": u["id"],
                "kind": "qualitative", "outcome_signal": bool(OUTCOME.search(u["raw_text"])), "raw_text": u["raw_text"], "start": 0,
                "end": len(u["raw_text"]), "table_id": None, "state": "unresolved"})
    from .table_facts import header_paths
    by_id={u["id"]:u for u in units}
    for table in tables:
        tcells=[by_id[i] for i in table["cell_ids"]]
        table["header_links"]={}
        for cell in tcells:
            above,left=header_paths(tcells,cell)
            table["header_links"][cell["id"]]={"column_header_ids":[x["id"] for x in above],
                                               "row_header_ids":[x["id"] for x in left]}
    return {"paper_id": paper_id, "source_sha256": source_hash, "representation_id": representation,
            "parser": parser, "pages": pages, "units": units, "tokens": tokens,
            "tables": tables, "candidates": candidates}
