"""Synthetic policy regressions; corpus accuracy is a separate measurement."""
from copy import deepcopy
import json
from pathlib import Path
import time
import pytest
from src.evidence.v2.contracts import coverage,identity
from src.evidence.v2.measurements import parse_measurement,range_problem
from src.evidence.v2.table_facts import build_table_facts,validate_relation,relation_for_cell
from src.evidence.v2.runtime import Config,cache_key,parse_bounded
from src.evidence.v2.runner import extract,interpret,strict_response
from src.evidence.v2.output import project_record,compatible_groups
from src.evidence.v2.repair import RepairBudget,validate_repair_result
from src.evidence.v2.store import project_from_store

def table_document(grid,caption="Table 1. Reported scores.",spans=None):
    units=[];cells=[];spans=spans or {}
    for r,row in enumerate(grid):
        for c,text in enumerate(row):
            if text is None:continue
            u={"id":f"t:r{r}:c{c}","source_sha256":"a"*64,"representation_id":"rep","paper_id":"p",
               "type":"table_cell","raw_text":text,"page":1,"bbox":[c*100,r*20,(c+1)*100,(r+1)*20],
               "row":r,"col":c,"row_span":spans.get((r,c),(1,1))[0],"col_span":spans.get((r,c),(1,1))[1],
               "table_id":"t","token_ids":[]}
            units.append(u);cells.append(u["id"])
    units.append({"id":"caption","source_sha256":"a"*64,"type":"caption","raw_text":caption,"page":1,"bbox":None})
    table={"id":"t","cell_ids":cells,"caption_id":"caption","notes":[],"caption":caption,
           "status":"inventoried","token_assignment_conflicts":[]}
    candidates=[{"id":u["id"]+":n","unit_id":u["id"],"table_id":"t","kind":"numeric","raw_text":u["raw_text"]}
                for u in units if u["type"]=="table_cell" and parse_measurement(u["raw_text"])]
    return {"paper_id":"p","source_sha256":"a"*64,"representation_id":"rep","units":units,
            "tables":[table],"tokens":[],"pages":[{"page":1,"status":"inventoried"}],"candidates":candidates}

def test_repeated_scores_distinct_subject_facts():
    d=table_document([["Method","Dice (%)"],["Alpha","81.9"],["Beta","81.9"]])
    f,_,_=build_table_facts(d)
    assert len(f)==len({x["id"] for x in f})==2
    assert {x["subject"] for x in f}=={"Alpha","Beta"}

@pytest.mark.parametrize("grid,count",[
    ([["Model","F1 (%)"],["Alpha","91.5"]],1),
    ([["Metric","Alpha","Beta"],["Dice (%)","81.9","82.1"]],2)])
def test_single_row_and_transposed(grid,count):
    assert len(build_table_facts(table_document(grid))[0])==count

def test_multilevel_merged_scope_preserved():
    d=table_document([["Method","Dataset A",None],[None,"Dice (%)","Accuracy (%)"],["Alpha","81.9","91.3"]],
                     spans={(0,0):(2,1),(0,1):(1,2)})
    f,_,_=build_table_facts(d);assert len(f)==2
    assert all(any(s["text"]=="Dataset A" for s in x["experimental_scope"]) for x in f)

@pytest.mark.parametrize("key,wrong",[("subject_id","t:r2:c0"),("metric_id","t:r0:c2")])
def test_existing_ids_do_not_license_wrong_cell(key,wrong):
    d=table_document([["Method","Dice (%)","Accuracy (%)"],["Alpha","81.9","91.5"],["Beta","83","92"]])
    e={u["id"]:u for u in d["units"]};t=d["tables"][0]
    p,_=relation_for_cell(t,[e[i] for i in t["cell_ids"]],e["t:r1:c1"])
    p[key]=wrong
    assert validate_relation(d,t,p)[1]==["wrong_row_column_or_metric_relationship"]

def test_scope_omission_and_foreign_source_blocked():
    d=table_document([["Method","Dataset A",None],[None,"Dice (%)","Accuracy (%)"],["Alpha","81.9","91.3"]],
                     spans={(0,0):(2,1),(0,1):(1,2)})
    e={u["id"]:u for u in d["units"]};t=d["tables"][0]
    p,_=relation_for_cell(t,[e[i] for i in t["cell_ids"]],e["t:r2:c1"])
    p["scope_ids"]=[]
    assert validate_relation(d,t,p)[1]==["essential_header_context_mismatch"]
    d["units"][0]["source_sha256"]="b"*64
    with pytest.raises(ValueError,match="Foreign source"):build_table_facts(d)

def test_cited_method_can_be_remeasured():
    d=table_document([["Method","Dice (%)"],["Baseline [9]","81.9"]],
                    "Table 1. We evaluate all methods on the same test set.")
    f=build_table_facts(d)[0][0]
    assert f["method_origin"]["citation_ids"]==["9"] and f["measurement_origin"]=="current_paper"
    d["units"][-1]["raw_text"]="Table 1. Scores from prior work."
    assert build_table_facts(d)[0][0]["measurement_origin"] is None

@pytest.mark.parametrize("raw,expected",[("-150",None),("1.1","r2_above_source_scale_maximum"),
                                        ("-12345%",None),("101%","r2_above_source_scale_maximum")])
def test_r2_unbounded_below(raw,expected):
    assert range_problem("r2",parse_measurement(raw))==expected

def test_decimal_ranges_qualifiers_uncertainty_and_ocr():
    m=parse_measurement("81.90 \u00b1 0.30*","%")
    assert (m["value"],m["uncertainty"],m["uncertainty_type"],m["footnote_marker"])==("81.90","0.30",None,"*")
    assert parse_measurement("up to 40%")["bound"]=="up to"
    assert parse_measurement("10\u201314%")["upper"]=="14"
    assert parse_measurement("0,87") is None
    assert parse_measurement("1,234.5")["value"]=="1234.5"
    assert parse_measurement("1e-6")["value"]=="0.000001"

def test_unresolved_footnotes_or_cell_overlap_block_acceptance():
    assert not build_table_facts(table_document([["Method","Dice (%)"],["Alpha","81.9*"]]))[0]
    d=table_document([["Method","Dice (%)"],["Alpha","81.9"]])
    d["tables"][0]["token_assignment_conflicts"]=["word"]
    assert not build_table_facts(d)[0]

def test_disabled_does_not_write(tmp_path):
    out=tmp_path/"absent"
    assert extract(Path("missing.pdf"),"p",out)["state"]=="disabled" and not out.exists()

def test_cache_tracks_structure_and_model_digest():
    d=table_document([["Method","Dice (%)"],["Alpha","81.9"]])
    key=cache_key(d,{"digest":"m1"},Config())
    d["units"][0]["raw_text"]="Dataset"
    assert cache_key(d,{"digest":"m1"},Config())!=key
    assert cache_key(d,{"digest":"m2"},Config())!=cache_key(d,{"digest":"m1"},Config())

def test_accounting_and_unresolved_completeness(tmp_path):
    d=table_document([["Method","Dice (%)"],["Alpha","81.9"]]);r=interpret(d,tmp_path)
    assert r["coverage"]["accounted"]==len(d["candidates"]) and r["coverage"]["semantic_complete"]
    d["units"].append({"id":"other","source_sha256":"a"*64,"type":"paragraph","raw_text":"17"})
    d["candidates"].append({"id":"uncertain","kind":"numeric","unit_id":"other","table_id":None})
    r=interpret(d,tmp_path/"partial")
    assert not r["coverage"]["semantic_complete"] and r["coverage"]["unresolved"]+r["coverage"]["deferred"]==1
    with pytest.raises(ValueError):coverage(d,[])

def test_output_no_legacy_bypass_or_provenance_loss(tmp_path):
    d=table_document([["Method","Dice (%)"],["Alpha","81.9"]]);r=interpret(d,tmp_path)
    old={"results":"Wrong 999%","summary":"Wrong 98%","key_findings":"Wrong 99%","inferences":"Wrong 3%"}
    out=project_record(old,r)
    assert "999" not in json.dumps(out) and "98%" not in json.dumps(out)
    row=out["quantitative_results"][0]
    assert row["method"]=="Alpha" and row["source"]["row"]==1
    assert row["source_lineage"]==out["scientific_facts"][0]["source_lineage"]
    assert old["results"]=="Wrong 999%"
    other=deepcopy(r["facts"][0]);other["experimental_scope"]=[{"text":"another dataset"}]
    assert len(compatible_groups([r["facts"][0],other]))==2

@pytest.mark.parametrize("content,done",[
    ('{"proposals":',True),(chr(96)*3+'json\n{"proposals":[]}\n'+chr(96)*3,True),('{"proposals":[]}',False)])
def test_malformed_or_truncated_response_never_salvaged(tmp_path,content,done):
    (tmp_path/"raw_response.ndjson").write_text(json.dumps({"message":{"content":content},
                       "done":done,"done_reason":"stop"})+"\n")
    with pytest.raises(ValueError):strict_response({"completion":{"done_reason":"stop"}},tmp_path)

def test_repair_bounds_and_provenance():
    b=RepairBudget()
    assert b.request("r1","missing_year","ocr")["state"]=="unresolved"
    assert b.request("r1","no_native_text","ocr")["state"]=="requested"
    assert b.request("r1","no_native_text","ocr")["state"]=="requested"
    assert b.request("r1","no_native_text","ocr")["state"]=="deferred"
    assert b.request("r2","unresolved_grid","structure")["state"]=="requested"
    assert b.request("r3","no_native_text","ocr")["state"]=="deferred"
    with pytest.raises(ValueError):validate_repair_result("source",{})

def test_real_parser_cancellation(tmp_path):
    start=time.monotonic()
    result,error=parse_bounded(tmp_path/"missing.pdf","p",tmp_path/"parse",.001)
    assert result is None and error in {"parser_timeout","parser_error"}
    assert time.monotonic()-start<5

def test_store_missing_never_falls_back(tmp_path):
    old={"paper_id":"p","results":"Unsafe 99%","summary":"Unsafe 99%"}
    out=project_from_store(old,{"document_sha256":"a"*64},tmp_path)
    assert out["results"]=="" and out["scientific_extraction"]["state"]=="deferred"

def test_native_single_row_table(tmp_path):
    import pymupdf
    from src.evidence.v2.inventory import inventory_pdf
    pdf=pymupdf.open();page=pdf.new_page();page.insert_text((50,60),"Table 1. Reported results.")
    xs=[50,200,300];ys=[80,110,140]
    for x in xs:page.draw_line((x,80),(x,140))
    for y in ys:page.draw_line((50,y),(300,y))
    for r,row in enumerate([["Method","Dice (%)"],["Alpha","81.9"]]):
        for c,text in enumerate(row):page.insert_text((xs[c]+5,ys[r]+20),text)
    path=tmp_path/"table.pdf";pdf.save(path);pdf.close()
    d=inventory_pdf(path,"p")
    assert len(d["pages"])==1 and d["tables"] and len(build_table_facts(d)[0])==1


def test_complete_cache_hit_and_tampered_fact_revalidated(tmp_path):
    d=table_document([["Method","Dice (%)"],["Alpha","81.9"]])
    cfg=Config(enabled=True,cache_directory=str(tmp_path/"cache"))
    first=interpret(d,tmp_path/"first",config=cfg)
    second=interpret(d,tmp_path/"second",config=cfg)
    assert second["cache_hit"] and second["requests"]==[]
    cache=next((tmp_path/"cache").rglob("complete.json"))
    saved=json.loads(cache.read_text(encoding="utf-8"))
    saved["result"]["facts"][0]["measurement"]["value"]="999"
    cache.write_text(json.dumps(saved),encoding="utf-8")
    third=interpret(d,tmp_path/"third",config=cfg)
    assert third["facts"][0]["measurement"]["value"]=="81.9"

def test_partial_result_not_reused_as_complete_cache(tmp_path):
    d=table_document([["Unknown","Unknown"],["Alpha","81.9"]])
    cfg=Config(enabled=True,cache_directory=str(tmp_path/"cache"))
    r=interpret(d,tmp_path/"partial",config=cfg)
    assert r["state"]=="partial" and not list((tmp_path/"cache").rglob("complete.json"))

def test_optional_api_sidecar_preserves_exact_facts_and_rejects_other_source(tmp_path):
    from src.evidence.monitor import atomic_json_write
    d=table_document([["Method","Dice (%)"],["Alpha","81.9"]])
    key=identity({"paper_id":"p"});out=tmp_path/key
    r=interpret(d,out)
    old={"paper_id":"p","summary":"Old 999%","results":"Old 999%"}
    projected=project_from_store(old,{"document_sha256":"a"*64},tmp_path)
    assert projected["scientific_facts"]==r["facts"]
    assert projected["quantitative_results"][0]["source"]["page"]==1
    bad=project_from_store(old,{"document_sha256":"b"*64},tmp_path)
    assert bad["results"]=="" and bad["scientific_extraction"]["state"]=="deferred"

def test_renderer_keeps_condition_negation_and_scope():
    from src.evidence.v2.output import render_fact
    f=build_table_facts(table_document([["Method","Dice (%)"],["Alpha","81.9"]]))[0][0]
    f["experimental_scope"]=[{"id":"scope","text":"Dataset A / held-out test"}]
    f["measurement"].update(bound="up_to",negated=True,conditions=["within five percent"],topic_qualifiers=[])
    rendered=render_fact(f)
    assert "up to" in rendered and "Not observed" in rendered and "Dataset A" in rendered and "within five percent" in rendered

def test_existing_prose_ownership_validator_is_reused_without_measurement_changes():
    from src.evidence.prose_attribution.source import SourceDocument
    from src.evidence.prose_attribution.inventory import inventory
    from src.evidence.prose_attribution.support import discourse,assess_claim
    from src.evidence.v2.prose_facts import adapt_supported_prose
    text="A farm used DeltaDrip's irrigation system. The farm reduced water use by 17%."
    source=SourceDocument.from_text("p",text,metadata={"source_kind":"narrative_overview"})
    numbers=inventory(source)
    proposed={"candidate_ids":[numbers[0]["id"]],"subject":"DeltaDrip","outcome":"water_use_reduction",
       "location":None,"year":None,"population":None,"claim_role":"cited_result",
       "measurement":{"kind":"scalar","value":17,"lower":None,"upper":None,"unit":"percent",
                      "qualifier":"exact","direction":"decrease","negated":False,"conditions":[]},
       "references":{k:["s001","s002"] for k in ("subject","measurement","ownership_bridge","context","population","condition","role")}}
    record=assess_claim(source,numbers,discourse(source,numbers),proposed,"c")
    assert record["published"]
    facts=adapt_supported_prose(source,{"accepted_claims":[record]})
    assert len(facts)==1 and facts[0]["measurement"]["value"]=="17"
    assert facts[0]["location"] is None and facts[0]["year"] is None
    assert record["measurement"]["value"]==17

def test_image_only_page_is_partial_not_successful_empty_document(tmp_path):
    import pymupdf
    from src.evidence.v2.inventory import inventory_pdf
    pdf=pymupdf.open();pdf.new_page();path=tmp_path/"blank.pdf";pdf.save(path);pdf.close()
    d=inventory_pdf(path,"p");r=interpret(d,tmp_path/"output")
    assert not r["coverage"]["processing_complete"] and r["state"]=="partial"

def test_numeric_experiment_condition_is_not_dropped_or_confused_with_neighbor_metric():
    d=table_document([["Method","Batch size","Dice (%)","Accuracy (%)"],
                      ["Alpha","32","81.9","91.5"]])
    facts=build_table_facts(d)[0]
    assert len(facts)==2
    for fact in facts:
        text=[x["text"] for x in fact["experimental_scope"]]
        assert "32" in text and "Batch size" in text
        assert "81.9" not in text and "91.5" not in text

def test_cell_unit_cannot_override_contradictory_metric_header():
    d=table_document([["Method","Dice (%)"],["Alpha","81.9 ms"]])
    assert not build_table_facts(d)[0]

def test_evaluation_cannot_promote_unreviewed_labels_or_slow_latency():
    from src.evaluation.evidence_v2 import score,promotion_gates
    assert score([],{"authority":"machine_assisted","targets":[{"eligible":True}]})["exact_tuple_recall"] is None
    gates=promotion_gates({"precision":1,"exact_tuple_recall":.8},
        {"precision":.99,"exact_tuple_recall":.81},
        timing={"scope":"uncached_end_to_end","paired_conditions_equal":True,
                "correct_coverage_not_worse":True,
                "baseline":{"p50_seconds":1,"p95_seconds":2},
                "current":{"p50_seconds":1,"p95_seconds":2.1}},
        fixtures=0,preservation=1)
    assert gates["gates"]["accepted_tuple_precision"]["verdict"]=="FAIL"
    assert gates["gates"]["uncached_p95"]["verdict"]=="FAIL"
    assert not gates["eligible_for_promotion"]

def test_outcome_priority_preserves_unselected_numeric_candidates(tmp_path,monkeypatch):
    from types import SimpleNamespace
    from src.evidence.v2 import semantic
    import src.evidence.prose_attribution.extractor as old
    chosen=[]
    monkeypatch.setattr(semantic,"local_tokenizer",lambda _:SimpleNamespace(encode=lambda _:[]))
    def fake_extract(source,*args,**kwargs):
        chosen.append(source.document_id)
        return {"accepted_claims":[]}
    monkeypatch.setattr(old,"extract_document",fake_extract)
    units=[{"id":"author","type":"paragraph","raw_text":"Author affiliation 7.","token_ids":[],
            "page":1,"bbox":None},
           {"id":"result","type":"paragraph","raw_text":"The method improved Dice to 81.9%.","token_ids":[],
            "page":2,"bbox":None}]
    d={"paper_id":"p","source_sha256":"a"*64,"units":units,"candidates":[
        {"id":"n1","unit_id":"author","kind":"numeric","table_id":None},
        {"id":"n2","unit_id":"result","kind":"numeric","table_id":None},
        {"id":"q2","unit_id":"result","kind":"qualitative","table_id":None,"outcome_signal":True}]}
    before=json.loads(json.dumps(d))
    semantic.resolve_prose(d,tmp_path,config=Config(enabled=True,local_model_enabled=True),
        model={"base_url":"http://localhost:11434","model":"qwen2.5:7b","tokenizer_path":str(tmp_path)},
        deadline=time.monotonic()+10)
    assert chosen[0]=="p:1" and set(chosen)=={"p:0","p:1"} and d==before


def test_host_checkpoint_precedes_model_failure(tmp_path,monkeypatch):
    from src.evidence.v2 import semantic
    d=table_document([["Method","Dice (%)"],["Alpha","81.9"]])
    def fail(*args,**kwargs):
        raise RuntimeError("transport unavailable")
    monkeypatch.setattr(semantic,"resolve_packets",fail)
    with pytest.raises(RuntimeError):
        interpret(d,tmp_path)
    checkpoint=json.loads((tmp_path/"partial_checkpoint.json").read_text(encoding="utf-8"))
    facts=[json.loads(line) for line in (tmp_path/"facts_before_model.jsonl").read_text(encoding="utf-8").splitlines()]
    assert checkpoint["state"]=="model_pending" and len(facts)==1
    assert not checkpoint["semantic_complete"] and not (tmp_path/"result.json").exists()

def test_owned_process_tree_cancellation_stops_redirected_interpreter(tmp_path):
    import subprocess,sys
    from src.evidence.v2.runtime import terminate_owned
    marker=tmp_path/"late.txt"
    child=subprocess.Popen([sys.executable,"-B","-c",
        "import pathlib,sys,time;time.sleep(1);pathlib.Path(sys.argv[1]).write_text('late')",str(marker)],
        stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    terminate_owned(child)
    child.communicate()
    time.sleep(1.2)
    assert child.poll() is not None and not marker.exists()


def test_r2_still_rejects_negative_uncertainty():
    assert range_problem("r2",parse_measurement("-150 +/- -2"))=="negative_uncertainty"

def test_roman_caption_and_explicit_continued_table_keep_source_scope(tmp_path):
    import pymupdf
    from src.evidence.v2.inventory import inventory_pdf
    pdf=pymupdf.open()
    for caption,score in [("TABLE IV. Reported held-out results.","81.9"),("TABLE IV (continued). Reported held-out results.","82.1")]:
        page=pdf.new_page();page.insert_text((50,60),caption)
        xs=[50,200,300];ys=[80,110,140]
        for x in xs:page.draw_line((x,80),(x,140))
        for y in ys:page.draw_line((50,y),(300,y))
        for r,row in enumerate([["Method","Dice (%)"],["Alpha",score]]):
            for c,text in enumerate(row):page.insert_text((xs[c]+5,ys[r]+20),text)
    path=tmp_path/"continued.pdf";pdf.save(path);pdf.close()
    document=inventory_pdf(path,"p")
    assert len(document["tables"])==2
    first,second=document["tables"]
    assert second["continuation_of"]==first["id"] and first["caption"].startswith("TABLE IV.")
    facts=build_table_facts(document)[0]
    assert len(facts)==2 and all("held-out" in f["caption"] for f in facts)


@pytest.fixture
def interrupted_sidecar(tmp_path,monkeypatch):
    import hashlib
    from src.evidence.v2 import runner,semantic
    from src.evidence.monitor import atomic_json_write
    source=tmp_path/"source.pdf";source.write_bytes(b"recorded source fixture")
    sha=hashlib.sha256(source.read_bytes()).hexdigest()
    document=table_document([["Method","Dice (%)"],["Alpha","81.9"]])
    document["source_sha256"]=sha
    for unit in document["units"]:unit["source_sha256"]=sha
    def parsed(source,paper_id,folder,seconds):
        atomic_json_write(folder/"parsed.json",document)
        return document,None
    def unavailable(*args,**kwargs):raise RuntimeError("transport unavailable")
    monkeypatch.setattr(runner,"parse_bounded",parsed)
    monkeypatch.setattr(semantic,"resolve_packets",unavailable)
    store=tmp_path/"sidecars";folder=store/identity({"paper_id":"p"})
    with pytest.raises(RuntimeError,match="transport unavailable"):
        extract(source,"p",folder,config=Config(enabled=True))
    return store,folder,sha


def test_opt_in_api_recovers_host_facts_after_model_interruption(tmp_path,interrupted_sidecar):
    from src.api.data import load_corpus
    store,folder,sha=interrupted_sidecar
    raw=tmp_path/"raw";processed=tmp_path/"processed";raw.mkdir();processed.mkdir()
    (raw/"collected_papers.json").write_text(json.dumps([{"paperId":"p","document_sha256":sha}]))
    (processed/"paper_summaries.json").write_text(json.dumps([{"paper_id":"p","results":"Legacy 999%"}]))
    (processed/"clusters.json").write_text("{}")
    cfg={"raw_metadata_dir":str(raw),"processed_dir":str(processed)}
    assert load_corpus(cfg)["papers"]["p"]["results"]=="Legacy 999%"
    before={str(p):p.read_bytes() for p in folder.rglob("*") if p.is_file()}
    out=load_corpus({**cfg,"scientific_results_dir":str(store)})["papers"]["p"]
    assert len(out["scientific_facts"])==1 and out["quantitative_results"][0]["value"]=="81.9"
    assert out["scientific_extraction"]["state"]=="partial"
    assert not out["scientific_extraction"]["coverage"]["processing_complete"]
    assert "999%" not in out["results"]
    assert before=={str(p):p.read_bytes() for p in folder.rglob("*") if p.is_file()}
    assert not (folder/"result.json").exists()


@pytest.mark.parametrize("tamper",["measurement","subject","decisions","source","invalid_final"])
def test_interrupted_checkpoint_rejects_changed_or_mismatched_evidence(interrupted_sidecar,tamper):
    store,folder,sha=interrupted_sidecar
    if tamper in {"measurement","subject"}:
        p=folder/"facts_before_model.jsonl";facts=[json.loads(x) for x in p.read_text().splitlines()]
        if tamper=="measurement":facts[0]["measurement"]["value"]="99"
        else:facts[0]["subject"]="Another method"
        p.write_text("\n".join(json.dumps(f) for f in facts)+"\n")
    elif tamper=="decisions":(folder/"decisions_before_model.jsonl").write_text("")
    elif tamper=="source":sha="b"*64
    else:(folder/"result.json").write_text("{}")
    out=project_from_store({"paper_id":"p","results":"Legacy 999%"},{"document_sha256":sha},store)
    assert out["scientific_facts"]==[] and out["scientific_extraction"]["state"]=="deferred"
    assert out["scientific_extraction"]["reason"]=="scientific_sidecar_identity_or_integrity_failure"
