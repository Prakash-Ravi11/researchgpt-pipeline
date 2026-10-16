"""Frozen-gate evaluation: unreviewed labels and stage timings never become accuracy."""
from collections import Counter
from decimal import Decimal
import math

FIELDS=("source_sha256","subject","metric","measurement","experimental_scope","measurement_origin","modality")

def tuple_key(fact):
    import json
    value={k:fact.get(k) for k in FIELDS}
    measurement=value.get("measurement") or {}
    value["measurement"]={k:measurement.get(k) for k in ("kind","value","lower","upper","unit","scale",
        "uncertainty","uncertainty_type","bound","direction","negated","conditions","topic_qualifiers")}
    if isinstance(value.get("experimental_scope"),list):
        value["experimental_scope"]=[x["text"] for x in value["experimental_scope"]]
    return json.dumps(value,sort_keys=True,ensure_ascii=False)

def score(predictions,labels):
    eligible=[x for x in labels["targets"] if x.get("eligible",True)]
    if labels.get("authority")!="independently_reviewed":
        return {"precision":None,"exact_tuple_recall":None,"eligible_targets":len(eligible),
                "accepted_predictions":len(predictions),"reason":"labels_not_independently_reviewed"}
    if any(x.get("review_status")!="verified" for x in eligible):
        return {"precision":None,"exact_tuple_recall":None,"eligible_targets":len(eligible),
                "accepted_predictions":len(predictions),"reason":"eligible_target_review_incomplete"}
    expected=Counter(tuple_key(x["fact"]) for x in eligible)
    actual=Counter(tuple_key(x) for x in predictions)
    correct=sum((expected & actual).values())
    return {"precision":correct/len(predictions) if predictions else None,
            "exact_tuple_recall":correct/len(eligible) if eligible else None,
            "correct":correct,"accepted_predictions":len(predictions),"eligible_targets":len(eligible),
            "unreturned_eligible_targets":len(eligible)-correct,
            "unmatched_predictions":len(predictions)-correct}

def percentile(values,p):
    if not values:return None
    ordered=sorted(values);position=(len(ordered)-1)*p
    low=int(position);high=math.ceil(position)
    return ordered[low]+(ordered[high]-ordered[low])*(position-low)

def latency(rows):
    values=[r["elapsed_seconds"] for r in rows]
    return {"runs":len(rows),"p50_seconds":percentile(values,.5),"p95_seconds":percentile(values,.95),
            "max_seconds":max(values) if values else None,
            "timeouts":sum(r.get("state")=="timeout" for r in rows),
            "partial":sum(r.get("partial",False) for r in rows)}

def promotion_gates(baseline,current,*,timing=None,fixtures=None,preservation=None):
    def gate(value,reason):return {"verdict":value,"reason":reason}
    gates={}
    for name,threshold in [("accepted_tuple_precision",.95),("exact_tuple_recall",.80)]:
        field="precision" if "precision" in name else "exact_tuple_recall"
        before,after=baseline.get(field),current.get(field)
        if before is None or after is None:
            gates[name]=gate("NOT MEASURED","Independent paired labels are unavailable or incomplete")
        else:gates[name]=gate("PASS" if after>=max(threshold,before) else "FAIL",
                              f"Frozen minimum {threshold}; baseline {before}; current {after}")
    gates["preservation"]=gate("NOT MEASURED" if preservation is None else
        "PASS" if preservation==1 else "FAIL","All independently correct baseline facts must survive")
    gates["zero_wrong_cell_metric_study"]=gate("NOT MEASURED" if fixtures is None else
        "PASS" if fixtures==0 else "FAIL","Frozen regression fixture error count")
    if not timing or timing.get("scope")!="uncached_end_to_end" or not timing.get("paired_conditions_equal"):
        gates["uncached_p50"]=gates["uncached_p95"]=gate("NOT MEASURED",
            "Parser/host diagnostics and cached replay are not paired uncached end-to-end model processing")
    else:
        for q in ["p50","p95"]:
            a,b=timing["baseline"][q+"_seconds"],timing["current"][q+"_seconds"]
            good=timing.get("correct_coverage_not_worse") and b is not None and a is not None and b<=a
            gates["uncached_"+q]=gate("PASS" if good else "FAIL","No latency allowance or coverage reduction")
    return {"gates":gates,"eligible_for_promotion":all(x["verdict"]=="PASS" for x in gates.values())}
