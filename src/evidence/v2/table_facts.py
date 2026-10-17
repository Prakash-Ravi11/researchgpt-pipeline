"""Resolve source header axes once; build values from cells, never model numbers."""
import re
from .contracts import identity, support, verify_document
from .measurements import metric_identity, parse_measurement, range_problem

SUBJECT_AXIS = re.compile(r"^(?:method|model|approach|system|intervention|algorithm|network|backbone)s?\b", re.I)

def _covers(cell, index, axis):
    key, span = ("col", "col_span") if axis == "col" else ("row", "row_span")
    return cell[key] <= index < cell[key] + cell.get(span, 1)

def header_paths(cells, value):
    numeric_rows=[c["row"] for c in cells if parse_measurement(c["raw_text"]) is not None]
    body_start=min(numeric_rows) if numeric_rows else max(c["row"] for c in cells)+1
    # Headers precede data. A missing value in an earlier data row is not a header.
    header_cells=[c for c in cells if c["row"]<body_start]
    above=[c for c in header_cells if c["row"]<value["row"] and
           _covers(c,value["col"],"col") and c["raw_text"].strip()]
    left=[]
    for c in cells:
        if c["col"]>=value["col"] or not _covers(c,value["row"],"row") or not c["raw_text"].strip():
            continue
        other_metric=any(metric_identity(h["raw_text"]) for h in header_cells
                         if _covers(h,c["col"],"col"))
        if other_metric and parse_measurement(c["raw_text"]) is not None:
            continue
        left.append(c)
    return sorted(above,key=lambda c:c["row"]),sorted(left,key=lambda c:c["col"])

def relation_for_cell(table, cells, value):
    above, left = header_paths(cells, value)
    column_metrics = [c for c in above if metric_identity(c["raw_text"])]
    row_metrics = [c for c in left if metric_identity(c["raw_text"])]
    if bool(column_metrics) == bool(row_metrics):
        return None, "missing_or_competing_metric_axis"
    metric = (column_metrics or row_metrics)[-1]
    subjects = left if column_metrics else above
    subjects = [c for c in subjects if not metric_identity(c["raw_text"]) and parse_measurement(c["raw_text"]) is None]
    if column_metrics:
        explicit = [c for c in subjects if any(
            SUBJECT_AXIS.search(h["raw_text"]) for h in cells
            if h["row"] < c["row"] and _covers(h, c["col"], "col"))]
        if len(explicit) == 1:
            subjects = explicit
        elif not explicit:
            return None, "subject_axis_not_established"
    else:
        if not any(re.match(r"^metric\b", c["raw_text"], re.I) for c in cells
                   if c["col"] == 0 and c["row"] < value["row"]):
            return None, "transposed_subject_axis_not_established"
    if len(subjects) != 1:
        return None, "ambiguous_subject_header_path"
    context=above+left
    for cell in left:
        if parse_measurement(cell["raw_text"]) is not None:
            context += [h for h in cells if h["row"]<cell["row"] and _covers(h,cell["col"],"col")
                        and parse_measurement(h["raw_text"]) is None and h["raw_text"].strip()]
    context=list({c["id"]:c for c in context}.values())
    return {"measurement_id": value["id"], "subject_id": subjects[0]["id"],
            "metric_id": metric["id"], "scope_ids": [c["id"] for c in context
                 if c["id"] not in {subjects[0]["id"], metric["id"]}],
            "ownership_ids": [], "relation": "reported_result"}, None

def validate_relation(document, table, proposal, evidence=None):
    evidence = evidence or verify_document(document)
    issues = []
    allowed = set(table["cell_ids"] + [table["caption_id"]] + table["notes"])
    ids = [proposal.get(k) for k in ("measurement_id", "subject_id", "metric_id")]
    scope = proposal.get("scope_ids", [])
    owners = proposal.get("ownership_ids", [])
    if not isinstance(scope, list) or not isinstance(owners, list):
        return None, ["malformed_reference_arrays"]
    if any(not isinstance(x, str) or x not in allowed for x in ids + scope + owners):
        return None, ["unknown_or_foreign_table_reference"]
    value, subject, metric = [evidence[x] for x in ids]
    if value["type"] != "table_cell":
        return None, ["measurement_not_a_cell"]
    expected, reason = relation_for_cell(table, [evidence[x] for x in table["cell_ids"]], value)
    if expected is None:
        return None, [reason]
    if any(proposal.get(k) != expected[k] for k in ("subject_id", "metric_id")):
        return None, ["wrong_row_column_or_metric_relationship"]
    # Omitting known experimental header context is not permitted.
    if set(scope) != set(expected["scope_ids"]):
        return None, ["essential_header_context_mismatch"]
    if table["status"] != "inventoried" or table["token_assignment_conflicts"]:
        return None, ["unresolved_token_cell_ownership"]
    header_text = " ".join(evidence[x]["raw_text"] for x in [metric["id"]] + scope)
    inherited_unit = "%" if "%" in header_text else next(
        (u for u in ("mm", "cm", "ms", "GB", "MB") if re.search(r"\b"+u+r"\b", header_text)), None)
    measurement = parse_measurement(value["raw_text"], inherited_unit, [metric["id"]] + scope)
    if measurement is None:
        return None, ["measurement_not_a_complete_source_expression"]
    if inherited_unit and measurement["unit"] != inherited_unit:
        return None, ["source_cell_header_unit_conflict"]
    name = metric_identity(metric["raw_text"])
    if name is None:
        return None, ["metric_identity_unresolved"]
    problem = range_problem(name, measurement)
    if problem:
        return None, [problem]
    if measurement["footnote_marker"]:
        marker = measurement["footnote_marker"]
        matching = [n for n in table["notes"] if evidence[n]["raw_text"].lstrip().startswith(marker)]
        if len(matching) != 1:
            return None, ["footnote_scope_unresolved"]
        scope = scope + matching
    # Citation presence identifies method citations; it does not establish measurement origin.
    caption = evidence[table["caption_id"]]["raw_text"]
    explicit_own = bool(re.search(r"\bwe (?:evaluate|measure|rerun) (?:all|both|each)\b", caption, re.I))
    explicit_own = explicit_own and not re.search(r"\b(?:except|literature|taken from|copied from|prior work)\b",caption,re.I)
    origin = "current_paper" if explicit_own else None
    fields = {k: support("supported", [ref], "Host-checked cell/header relationship")
              for k, ref in [("subject", subject["id"]), ("metric", metric["id"]),
                             ("measurement", value["id"])]}
    fields["experimental_scope"] = support("supported", scope + [table["caption_id"]],
                                         "Complete source header paths and caption retained")
    fields["measurement_origin"] = support("supported" if origin else "unresolved",
        [table["caption_id"]], "Explicit evaluation statement" if origin else
        "Table location and method citations do not establish who measured the result")
    context_state = "unresolved" if re.search(r"\b(?:year|location|deployment|site|survey)\b",header_text+" "+caption,re.I) else "inapplicable"
    fields["location"] = support(context_state, reason="No source-supported event location asserted")
    fields["year"] = support(context_state, reason="Publication year is not experiment year; no event association inferred")
    lineage = {"source": document["source_sha256"], "representation": document["representation_id"],
               "value": value["id"], "subject": subject["id"], "metric": metric["id"],
               "scope": scope}
    fact = {"id": identity(lineage), "paper_id": document["paper_id"], "kind": "numeric",
        "source_sha256":document["source_sha256"], "category": "source_reported", "subject": subject["raw_text"], "metric": name,
        "metric_label": metric["raw_text"], "measurement": measurement,
        "experimental_scope": [{"id": x, "text": evidence[x]["raw_text"]} for x in scope],
        "caption": caption, "reporting_source": document["source_sha256"],
        "measurement_origin": origin, "method_origin": {"citation_ids": re.findall(r"\[(\d+)\]", subject["raw_text"]),
                                                     "origin": None},
        "modality": "reported", "location": None, "year": None,
        "field_support": fields, "evidence_ids": ids + scope + [table["caption_id"]],
        "source_lineage": lineage, "decision": "accepted",
        "source": {"page": value["page"], "table_id": table["id"], "cell_id": value["id"],
                   "row": value["row"], "col": value["col"], "bbox": value["bbox"]}}
    return fact, issues

def build_table_facts(document):
    evidence = verify_document(document)
    facts, cell_decisions, packets = [], {}, []
    for table in document["tables"]:
        cells = [evidence[x] for x in table["cell_ids"]]
        pending = []
        for cell in cells:
            if parse_measurement(cell["raw_text"]) is None:
                continue
            proposal, reason = relation_for_cell(table, cells, cell)
            fact, errors = validate_relation(document, table, proposal, evidence) if proposal else (None, [reason])
            if fact:
                facts.append(fact); cell_decisions[cell["id"]] = ("processed", "host_validated_table_relation", [fact["id"]])
            else:
                cell_decisions[cell["id"]] = ("unresolved", errors[0], [])
                pending.append(cell["id"])
        if pending:
            packets.append({"id": table["id"] + ":relations", "kind": "table",
                            "table_id": table["id"], "measurement_ids": pending,
                            "evidence_ids": table["cell_ids"] + [table["caption_id"]] + table["notes"]})
    # Numeric settings are processed context, not silently discarded or counted as outcomes.
    for fact in facts:
        for item in fact["experimental_scope"]:
            if item["id"] in evidence and parse_measurement(evidence[item["id"]]["raw_text"]) is not None:
                previous=cell_decisions.get(item["id"])
                if previous and previous[0]=="unresolved":
                    cell_decisions[item["id"]]=("processed","source_supported_experimental_setting",[fact["id"]])
    for packet in packets:
        packet["measurement_ids"]=[i for i in packet["measurement_ids"] if cell_decisions[i][0]=="unresolved"]
    packets=[p for p in packets if p["measurement_ids"]]
    return facts, cell_decisions, packets
