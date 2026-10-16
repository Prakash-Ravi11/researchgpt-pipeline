"""Decimal-safe source parsing; range checks never establish attribution."""
from decimal import Decimal, InvalidOperation
import re

NUMBER = r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?"
SCALAR = re.compile(r"^\s*(?P<bound><=|>=|<|>|\u2264|\u2265|~|\u2248|up to|approximately|about)?\s*"
    r"(?P<value>" + NUMBER + r")"
    r"(?:\s*(?P<join>\u00b1|\+/-|\u2013|\u2014|to|-)\s*(?P<other>" + NUMBER + r"))?"
    r"\s*(?P<unit>%|mm|cm|ms|s|kg|GB|MB|USD)?\s*(?P<marker>[*\u2020\u2021a-z]?)\s*$", re.I)

def parse_measurement(raw, inherited_unit=None, unit_refs=()):
    text = raw.replace("\u2212", "-")
    if "," in text:
        grouping = re.sub(r"(?<![0-9.])[0-9]{1,3}(?:,[0-9]{3})+(?:\.[0-9]+)?", lambda m: m.group().replace(",", ""), text)
        if "," in grouping:
            return None
        text = grouping
    m = SCALAR.fullmatch(text)
    if not m:
        return None
    try:
        value = Decimal(m["value"])
        other = Decimal(m["other"]) if m["other"] is not None else None
        if not value.is_finite() or other is not None and not other.is_finite():
            return None
    except InvalidOperation:
        return None
    unit = m["unit"] or inherited_unit
    join = m["join"]
    kind = "uncertainty" if join in ("\u00b1", "+/-") else "range" if join else "scalar"
    if kind == "range" and value > other:
        return None
    return {"raw": raw, "kind": kind, "value": str(value) if kind != "range" else None,
            "lower": str(value) if kind == "range" else None,
            "upper": str(other) if kind == "range" else None,
            "uncertainty": str(other) if kind == "uncertainty" else None,
            "uncertainty_type": None, "bound": m["bound"], "unit": unit,
            "scale": "percent" if unit == "%" else "source_reported",
            "unit_evidence_ids": list(unit_refs) if not m["unit"] else [],
            "footnote_marker": m["marker"] or None}

def metric_identity(label):
    text = label.casefold().replace("\u00b2", "2").replace("^", "")
    names = {"r2": r"\br2\b|r[- ]squared",
             "dice": r"\bdice\b|\bdsc\b", "accuracy": r"\baccuracy\b",
             "f1": r"\bf1\b", "precision": r"\bprecision\b",
             "recall": r"\brecall\b|\bsensitivity\b",
             "specificity": r"\bspecificity\b", "auc": r"\bauc\b|\bauroc\b",
             "hd95": r"\bhd95\b|\b95hd\b", "iou": r"\biou\b|\bjaccard\b",
             "em": r"\bexact match\b|\bem\b", "rmse": r"\brmse\b",
             "mae": r"\bmae\b", "bleu": r"\bbleu\b"}
    hits = [name for name, pattern in names.items() if re.search(pattern, text)]
    return hits[0] if len(hits) == 1 else None

def range_problem(metric, measurement):
    vals = [Decimal(measurement[k]) for k in ("value", "lower", "upper")
            if measurement.get(k) is not None]
    if metric == "r2":
        # Predictive R2 has no finite lower bound. Percent scaling must be explicit.
        maximum = Decimal(100 if measurement["unit"] == "%" else 1)
        return "r2_above_source_scale_maximum" if any(v > maximum for v in vals) else None
    if metric in {"dice", "accuracy", "f1", "precision", "recall", "specificity", "auc", "iou", "em"}:
        if any(v < 0 for v in vals):
            return "negative_bounded_metric"
        if measurement["unit"] == "%" and any(v > 100 for v in vals):
            return "percent_metric_above_100"
    if metric in {"hd95", "rmse", "mae"} and any(v < 0 for v in vals):
        return "negative_distance_or_error"
    if measurement.get("uncertainty") is not None and Decimal(measurement["uncertainty"]) < 0:
        return "negative_uncertainty"
    return None
