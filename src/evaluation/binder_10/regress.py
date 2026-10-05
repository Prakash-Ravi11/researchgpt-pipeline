"""Regression for the precision-first binder rewrite (synthetic chunks only). Every reviewer reproduction must come out
NOT bound, or bound only to the claim's true cell; the spec-conformance, LLM and robustness probes have exact
expectations. Run from the repo root:  .venv/Scripts/python.exe -B <this file>"""
import importlib.util
import json
import os
import random
import sys
import tempfile
import time

SP = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.getcwd())
import src.evidence  # noqa: E402,F401
import src.evidence.binder_v2 as B
import src.evidence.gate as G  # noqa: E402
import yaml  # noqa: E402
B._llm_cfg = lambda: yaml.safe_load(open("configs/staging_config.yaml", encoding="utf-8"))["llm"]  # scratch copy only

os.environ.update(RGPT_BINDER_POLICY="v2", RGPT_FALLTHROUGH_POLICY="table_value_guard")
os.environ.pop("RGPT_BINDER_V2_DISABLE", None)
FAIL = []


def chunk(i, text, btype="paragraph", cells=None, page=1):
    c = {"chunk_id": f"SYN:{i}#0", "paper_id": "SYN", "source": "t", "representation": "pdf", "section": "results",
         "page_or_node": f"p{page}", "block_id": f"SYN:{i}", "block_type": btype, "char_start": 0,
         "char_end": len(text), "text": text}
    if cells:
        c.update(table_cells=cells, table_caption=text)
    return c


def table(i, caption, rows, cols, values, page=1):
    cells = [{"row_label": rows[r], "column_header": cols[k], "value": v, "caption": caption, "section": "results",
              "page": page, "row": r + 1, "col": k + 1}
             for r in range(len(rows)) for k, v in enumerate(values[r]) if v is not None]
    return chunk(i, caption, "table", cells, page)


def bind(claim, chunks, off=""):
    os.environ["RGPT_BINDER_V2_DISABLE"] = off
    B._CACHE.clear()
    return G.structural_bind(claim, chunks)


def cells(sb):
    return [(b["number"], b["cell"]["row"], b["cell"]["col"], b["cell"]["value"]) for b in sb.get("bindings") or []] \
        if sb["status"] == "bound" else []


def check(tag, ok, got):
    print(f"{'PASS' if ok else 'FAIL'}  {tag}: {got}")
    if not ok:
        FAIL.append(tag)


def expect(tag, claim, chunks, status=None, bound=None, off=""):
    """status: the exact expected status; bound: the exact expected bindings [(number, row, col, value)]."""
    sb = bind(claim, chunks, off)
    got = cells(sb) or sb["status"]
    ok = (bound is not None and cells(sb) == bound) or (status is not None and sb["status"] == status)
    check(tag, ok, got)
    return sb


# --- A. the 34 precision reproductions (review/precision/repro.py): never bound to a wrong cell ----------------------
import types  # noqa: E402
hmod = types.ModuleType("regress_h")
hmod.B, hmod.bind, hmod.chunk, hmod.table = B, bind, chunk, table
sys.modules["regress_h"] = hmod
src = open(os.path.join(SP, "review", "precision", "repro.py"), encoding="utf-8").read()
ns = {"__name__": "repro_cases", "__file__": os.path.join(SP, "review", "precision", "repro.py")}
exec(src.split("\n\ndef res(")[0].replace("from h import B, bind, chunk, table  # noqa: E402",
                                           "from regress_h import B, bind, chunk, table"), ns)
ALLOWED = {"THR2": [("0.81", "UNet", "Dice", "0.81")], "DOM1": [("0.923", "CSF", "Ours", "0.923")]}
for tag, claim, ch in ns["R"]:
    sb = bind(claim, ch)
    got = cells(sb)
    check(f"A {tag}", not got or got == ALLOWED.get(tag), got or sb["status"])

# --- B. spec conformance -------------------------------------------------------------------------------------------
T = table(1, "Table 1: Segmentation results.", ["UNet", "VNet"], ["Dice"], [["0.81"], ["0.84"]])
TA = table(10, "Table 10: Results on BraTS.", ["Ours"], ["Dice"], [["0.95"]], page=10)
TB = table(11, "Table 11: Results on ISLES.", ["Ours"], ["Dice"], [["0.95"]], page=11)
expect("B caption names the dataset", "Ours achieves a Dice of 0.95 on BraTS.", [TA, TB],
       bound=[("0.95", "Ours", "Dice", "0.95")])
TC = table(12, "Table 12: Results on set A.", ["Ours"], ["Dice"], [["0.87 ± 0.06"]], page=12)
TD = table(13, "Table 13: Results on set A.", ["Ours"], ["Dice"], [["0.87"]], page=13)
expect("B ± is not a tie-break", "Ours achieves a Dice of 0.87 ± 0.06.", [TC, TD], status="duplicate_quantity_context")
TE = table(20, "Table 2: Results.", ["Ours"], ["Dice"], [["0.95"]], page=20)
TF = table(21, "Table 3: Results.", ["Ours"], ["Dice"], [["0.95"]], page=21)
expect("B table mention picks", "As shown in Table 2, ours achieves a Dice of 0.95.", [TE, TF],
       bound=[("0.95", "Ours", "Dice", "0.95")])
sb = bind("As shown in Table 2, ours achieves a Dice of 0.95.", [TE, TF])
check("B table mention picks Table 2", sb.get("cell", {}).get("caption") == "Table 2: Results.", sb.get("cell"))
expect("B table_mention off: no dominance either", "As shown in Table 2, ours achieves a Dice of 0.95.", [TE, TF],
       status="duplicate_quantity_context", off="table_mention")
TCOL = table(2, "Table 2: Average Dice scores per structure.", ["CSF", "Average"], ["Ours", "nnU-Net"],
             [["0.923 ± 0.006", "0.897 ± 0.011"], ["0.926 ± 0.012", "0.920 ± 0.014"]], page=2)
expect("B D9 0.915 (no cell) not required", "Our method achieves an average Dice score of 0.926 ± 0.012 versus 0.915 "
       "for nnU-Net.", [TCOL], bound=[("0.926", "Average", "Ours", "0.926 ± 0.012")])
T2 = table(3, "Table 1: Results.", ["Ours", "UNet"], ["Dice"], [["0.90"], ["0.85"]])
expect("B threshold, no metric named", "Our method achieves above 0.90 versus 0.85 for UNet.", [T2], status="not_bindable")
expect("B threshold alone", "Our method achieves above 0.90.", [T2], status="not_a_table_claim")
expect("B threshold beside a comparator", "Our method achieves a Dice above 0.90 versus 0.85 for UNet.", [T2],
       bound=[("0.85", "UNet", "Dice", "0.85")])
expect("B different entity -> wrong_cell", "VNet obtains a Dice of 0.81.", [T], status="wrong_cell")
it = G._gate_value("results", "VNet obtains a Dice of 0.81.", [T], [])
check("B gate binding_wrong_cell", it["abstain_reason"] == "binding_wrong_cell", it["abstain_reason"])
T5 = table(5, "Table 1: Results.", ["Ours"], ["Dice"], [["0.90"]], page=1)
T6 = table(6, "Table 2: Results.", ["Ours"], ["Precision"], [["0.90"]], page=2)
expect("B two quantities, one value", "Ours achieves a Dice and a precision of 0.90.", [T5, T6], status="wrong_cell")
for hdr in ("Dice score", "Dice coefficient", "Dice similarity coefficient", "DSC", "Dice"):
    TS = table(1, "Table 1: Segmentation results.", ["Ours", "UNet"], [hdr], [["0.87"], ["0.81"]])
    for c in ("Ours achieves a Dice of 0.87.", "Ours achieves a DSC of 0.87."):
        expect(f"B synonym {hdr!r} / {c[14:18]}", c, [TS], bound=[("0.87", "Ours", hdr, "0.87")])
TS = table(1, "Table 1: Segmentation results.", ["Ours", "UNet"], ["Dice"], [["0.87"], ["0.81"]])
expect("B % never a fraction", "Ours achieves a Dice of 0.87%.", [TS], status="wrong_cell")
TS = table(1, "Table 1: Segmentation results.", ["Ours", "UNet"], ["Dice (%)"], [["0.87"], ["0.81"]])
expect("B % stated in the header", "Ours achieves a Dice of 0.87%.", [TS], bound=[("0.87", "Ours", "Dice (%)", "0.87")])
TT = table(4, "Table 4: Prior work.", ["Smith et al. (2020)"], ["Results"], [["DSC: 83.79%, VS: 84.84%, HD95: 35.66 mm"]])
expect("B part unit mm", "Smith et al. (2020) reported an HD95 of 35.66 mm.", [TT],
       bound=[("35.66", "Smith et al. (2020)", "Results", "DSC: 83.79%, VS: 84.84%, HD95: 35.66 mm")])
expect("B part unit % vs mm", "Smith et al. (2020) reported an HD95 of 35.66%.", [TT], status="wrong_cell")
for hdr, ok in (("# subjects", True), ("#subjects", True), ("No. of subjects", True), ("Number of subjects", True),
                ("n", True), ("# participants", False), ("Number of scans", False)):
    TN = table(6, "Table 6: Summary of the data used.", ["Training", "Testing"], [hdr, "Age (years)"],
               [["15", "28.7"], ["18", "30.1"]])
    sb = bind("Our training set contains 15 subjects.", [TN])
    check(f"B count header {hdr!r}", (sb["status"] == "bound") == ok, cells(sb) or sb["status"])
check("B Eq. numbers", [m["tok"] for m in B.mentions("Using Eq. (12), Ours reaches a Dice of 0.87.")] == ["0.87"]
      and [m["tok"] for m in B.mentions("Using Eq. 12, Ours reaches a Dice of 0.87.")] == ["0.87"], "Eq.")
TQ = table(1, "Table 1: Results.", ["Ours", "UNet"], ["Dice", "Epochs"], [["0.87", "12"], ["0.81", "40"]])
expect("B epochs of the other row", "Ours is trained with the loss of Eq. (12) for 40 epochs.", [TQ], status="wrong_cell")
expect("B Eq. only", "Ours minimizes the loss in Eq. (12) over all epochs.", [TQ], status="no_number")
P = [chunk(0, "We present a comparison with UNet on two public datasets."),
     table(1, "Table 1: Segmentation results.", ["UNet", "FooNet"], ["Dice"], [["0.81"], ["0.87"]])]
B._CACHE.clear()
check("B 'we present a comparison' declares nothing", B._index(P, frozenset())["declared"] == {}, "")
expect("B own ref, no own cell", "Our method achieves a Dice of 0.81.", P, status="wrong_cell")
P = [chunk(0, "We propose AlphaNet. We also introduce BetaLoss, a new boundary loss."),
     table(1, "Table 1: Segmentation results.", ["AlphaNet", "UNet"], ["Dice"], [["0.90"], ["0.85"]])]
expect("B two declared names", "Our model achieves a Dice of 0.90.", P, status="ambiguous_subject")
P = [chunk(0, "In our experiments UNet performs well on large lesions."),
     table(1, "Table 1: Segmentation results.", ["UNet", "VNet"], ["Dice"], [["0.81"], ["0.84"]])]
expect("B no verb alias", "The network performs with a Dice of 0.81 on the test set.", P, status="not_bindable")
P = [chunk(0, "Unexposed controls were scanned twice."),
     table(1, "Table 1: Brain volumes.", ["Unexposed", "Exposed"], ["Volume (cm3)"], [["412.5"], ["398.1"]])]
for off in ("", "own_alias"):
    sb = expect(f"B group alias (off={off!r})", "The controls had a mean volume of 412.5 cm3.", P,
                bound=[("412.5", "Unexposed", "Volume (cm3)", "412.5")], off=off)
check("B group alias span", (sb.get("bindings") or [{}])[0].get("alias_span") == "Unexposed controls were scanned twice.",
      (sb.get("bindings") or [{}])[0].get("alias_span"))
TF2 = table(1, "Table 1: Performance of FooNet and baselines.", ["FooNet", "UNet"], ["Dice", "Sensitivity"],
            [["0.87", "0.91"], ["0.81", "0.87"]])
expect("B subject is not the quantity", "FooNet achieves a specificity of 0.91.", [TF2], status="not_bindable")
TM = table(1, "Table 1: Dice scores per structure.", ["CSF", "GM"], ["UNet", "VNet"], [["0.81", "0.84"], ["0.77", "0.79"]])
expect("B methods as columns", "VNet obtains a Dice of 0.84.", [TM], bound=[("0.84", "CSF", "VNet", "0.84")])
TP = table(1, "Table 1: Results by patch size.", ["Ours"], ["64", "128"], [["0.85", "0.88"]])
expect("B numeric column label", "With 128 pixel patches, Ours reaches 0.88.", [TP], bound=[("0.88", "Ours", "128", "0.88")])
expect("B numeric column label conflict", "With 128 pixel patches, Ours reaches 0.85.", [TP], status="wrong_cell")
check("B mL", [(m["tok"], m["unit"]) for m in B.mentions("a volume of 12.5 mL")] == [("12.5", "ml")], "")
TV = table(1, "Table 1: Volumes.", ["Ours", "UNet"], ["Volume (cm3)"], [["12.5"], ["11.9"]])
expect("B mL vs cm3 header", "Ours estimates a volume of 12.5 mL.", [TV], status="wrong_cell")
check("B Tables 2 and 3", B._tables_named("As shown in Tables 2 and 3, ours reaches 0.95.") == {"2", "3"}, "")
TE2 = table(20, "Table 2: Results.", ["Ours"], ["Dice"], [["0.91"]], page=20)
TF3 = table(21, "Table 3: Results.", ["Ours"], ["HD95"], [["0.95"]], page=21)
expect("B Tables 2 and 3 -> 3", "As shown in Tables 2 and 3, ours reaches an HD95 of 0.95.", [TE2, TF3],
       bound=[("0.95", "Ours", "HD95", "0.95")])
expect("B Table 2 named, value in 3", "As shown in Table 2, ours reaches an HD95 of 0.95.", [TE2, TF3], status="wrong_cell")
TR = table(1, "Table 1: Demographics.", ["Age (years)", "Height (cm)"], ["Controls", "Cases"], [["28.7", "30.1"], ["172", "169"]])
expect("B row unit conflict", "Controls had a mean age of 28.7 weeks.", [TR], status="wrong_cell")
expect("B row quantity (transposed)", "Controls had a mean age of 28.7 years.", [TR],
       bound=[("28.7", "Age (years)", "Controls", "28.7")])
TI = table(1, "Table 1: Timing.", ["Ours", "UNet"], ["Inference time"], [["35.66 ms"], ["41.20 ms"]])
expect("B cell unit conflict", "Ours has an inference time of 35.66 s.", [TI], status="wrong_cell")
expect("B cell unit", "Ours has an inference time of 35.66 ms.", [TI], bound=[("35.66", "Ours", "Inference time", "35.66 ms")])
TW = table(1, "Table 1: Segmentation results.", ["This work", "UNet"], ["Dice"], [["0.87"], ["0.81"]])
expect("B 'this work' is not own (PREREG D5)", "Our method achieves a Dice of 0.87.", [TW], status="wrong_cell")
expect("B 'but' splits clauses: 0.84 names no metric", "UNet reaches a Dice of 0.81 but VNet reaches 0.84.", [T],
       status="partial_binding")
expect("B 'while' clause, metric shared", "UNet reaches a Dice of 0.81 while VNet reaches a Dice of 0.84.", [T],
       bound=[("0.81", "UNet", "Dice", "0.81"), ("0.84", "VNet", "Dice", "0.84")])
T3 = table(3, "Table 3: Results per dataset.", ["Ours", "VNet"], ["BraTS / Dice", "ISLES / Dice"], [["0.91", "0.88"], ["0.89", "0.86"]], page=3)
for c, exp in (("On ISLES, ours reaches a Dice of 0.91.", "wrong_cell"), ("Ours reaches a Dice of 0.91 on ISLES.", "wrong_cell"),
               ("For the ISLES dataset, ours reaches a Dice of 0.91.", "wrong_cell"),
               ("On BraTS, ours reaches a Dice of 0.91.", [("0.91", "Ours", "BraTS / Dice", "0.91")])):
    expect(f"B qualifier {c[:22]!r}", c, [T3], **({"status": exp} if isinstance(exp, str) else {"bound": exp}))
T4 = table(1, "Table 1: Results.", ["U-Net", "Attention U-Net"], ["Dice"], [["0.81"], ["0.85"]])
expect("B maximal match", "Attention U-Net reaches a Dice of 0.85.", [T4], bound=[("0.85", "Attention U-Net", "Dice", "0.85")])
expect("B maximal match, inner label", "Attention U-Net reaches a Dice of 0.81.", [T4], status="wrong_cell")
expect("B passive 'by'", "A Dice of 0.84 was obtained by VNet.", [T], bound=[("0.84", "VNet", "Dice", "0.84")])
expect("B 'X (a) outperforms Y (b)'", "Ours (0.90) outperforms UNet (0.85) in Dice.", [T2],
       bound=[("0.90", "Ours", "Dice", "0.90"), ("0.85", "UNet", "Dice", "0.85")])
expect("B 'respectively' lists abstain", "UNet and VNet obtain a Dice of 0.81 and 0.84, respectively.", [T],
       status="wrong_cell")
expect("B delta never binds", "Ours improves the Dice by 0.84 over UNet.", [T], status="not_a_table_claim")
P = [chunk(0, "In our experiments UNet performs well on large lesions."),
     table(1, "Table 1: Segmentation results.", ["UNet", "FooNet"], ["Dice"], [["0.81"], ["0.87"]])]
expect("B own claim, non-own cell", "Our network performs with a Dice of 0.81 on small lesions.", P, status="wrong_cell")

# --- C. the LLM judge (stubbed; the cache in replay mode) -----------------------------------------------------------
P = [chunk(0, "The baseline network UNet is widely used."), T]
calls = []
real = B._llm_call
B._llm_call = lambda req: calls.append(req) or {"choice": next(c["id"] for c in req["candidates"] if c["row"] == "UNet"),
                                                 "span": "The baseline network UNet is widely used."}
B._CACHE.clear()
sb = B.structural_bind_v2("The baseline network achieves a Dice of 0.81.", P, llm=True)
check("C alias judge binds with a verbatim span", cells(sb) == [("0.81", "UNet", "Dice", "0.81")] and len(calls) == 1
      and sb["bindings"][0]["subject"] == "llm_alias", (cells(sb) or sb["status"], len(calls)))
B._llm_call = lambda req: {"choice": "k1", "span": "VNet is a network."}
sb = None
try:
    sb = B.structural_bind_v2("The baseline network achieves a Dice of 0.81.", P, llm=True)
    check("C alias span not in the paper -> STOP", False, sb["status"])
except B.LLMViolation as e:
    check("C alias span not in the paper -> STOP", True, str(e)[:60])
B._llm_call = lambda req: {"choice": "k1", "span": "The baseline network UNet"}
P2 = [chunk(0, "The baseline network UNet is widely used. VNet is newer."), T]
sb = B.structural_bind_v2("The baseline network achieves a Dice of 0.84.", P2, llm=True)
check("C alias span must name the chosen cell", sb["status"] != "bound", sb["status"])
B._llm_call = lambda req: {"choice": "k1", "span": "The baseline network achieves a Dice of 0.81."}
try:
    sb = B.structural_bind_v2("The baseline network achieves a Dice of 0.81.", P, llm=True)
    check("C claim-only span -> STOP (PREREG E)", False, sb["status"])
except B.LLMViolation as e:
    check("C claim-only span -> STOP (PREREG E)", True, str(e)[:60])
T9 = table(9, "Table 9: Detection results.", ["UNet", "VNet"], ["mAP"], [["0.85"], ["0.85"]])
B._llm_call = lambda req: {"choice": "k1", "span": ""}
sb = B.structural_bind_v2("UNet and VNet both reach a mAP of 0.85.", [chunk(0, "UNet and VNet are compared."), T9], llm=True)
check("C empty span: rejected, no STOP", sb["status"] == "ambiguous_subject", sb["status"])
B._llm_call = lambda req: {"choice": "k1"}
sb = B.structural_bind_v2("UNet and VNet both reach a mAP of 0.85.", [chunk(0, "UNet and VNet are compared."), T9], llm=True)
check("C missing span: rejected", sb["status"] == "ambiguous_subject", sb["status"])
B._llm_call = lambda req: None
sb = B.structural_bind_v2("UNet and VNet both reach a mAP of 0.85.", [chunk(0, "x"), T9], llm=True)
check("C judge unavailable", sb["status"] == "ambiguous_subject" and sb["v2_trace"]["mentions"][0]["llm"]["result"] == "llm_error",
      sb["v2_trace"]["mentions"][0].get("llm"))
B._llm_call = real
with tempfile.TemporaryDirectory() as d:
    cache = os.path.join(d, "c.jsonl")
    with open(cache, "w", encoding="utf-8") as f:
        f.write("not json\n{\"run\": \"fresh\"}\n")
    os.environ.update(RGPT_BINDER_LLM_MODE="replay", RGPT_BINDER_LLM_CACHE=cache)
    B._LLM_MEM.clear()
    sb = B.structural_bind_v2("UNet and VNet both reach a mAP of 0.85.", [chunk(0, "x"), T9], llm=True)
    check("C replay cache miss, malformed lines skipped", sb["status"] == "ambiguous_subject"
          and sb["v2_trace"]["mentions"][0]["llm"]["result"] == "cache_miss", sb["v2_trace"]["mentions"][0].get("llm"))
    os.environ.pop("RGPT_BINDER_LLM_MODE"), os.environ.pop("RGPT_BINDER_LLM_CACHE")
    B._LLM_MEM.clear()

# --- D. unicode and odd text -------------------------------------------------------------------------------------
PD = [chunk(0, "We compare UNet and VNet on detection."), T9]
for c in ("In İzmir, a mAP of 0.85 for UNet, unlike VNet.", "On the İzmir cohort, the mAP of UNet is 0.85."):
    sb = bind(c, PD)
    check(f"D {c[:24]!r}", cells(sb) == [("0.85", "UNet", "mAP", "0.85")], cells(sb) or sb["status"])
TN2 = table(1, "Table 1: Correlation with age.", ["UNet", "VNet"], ["Pearson r"], [["0.45"], ["−0.12"]])
expect("D sign: -0.45 vs 0.45", "UNet shows a Pearson r of −0.45.", [TN2], status="not_a_table_claim")
expect("D sign: -0.12", "VNet shows a Pearson r of -0.12.", [TN2], bound=[("-0.12", "VNet", "Pearson r", "−0.12")])
expect("D sign: 0.12 vs -0.12", "VNet shows a Pearson r of 0.12.", [TN2], status="not_a_table_claim")
expect("D ligature", "UNet obtains a ﬁnal Dice of 0.81.", [T], bound=[("0.81", "UNet", "Dice", "0.81")])
expect("D wrapped cell", "VNet obtains a Dice of 0.947.",
       [table(1, "Table 1: Results.", ["UNet", "VNet"], ["Dice"], [["0.81"], ["0.94 7"]])], bound=[("0.947", "VNet", "Dice", "0.94 7")])
expect("D thousands", "The training set contains 1,500 images.",
       [table(6, "Table 6: Data.", ["Training"], ["Number of images"], [["1500"]])], bound=[("1500", "Training", "Number of images", "1500")])
for n in (2000, 40000):
    t0 = time.perf_counter()
    sb = bind("UNet obtains a Dice of 0.81" + " " * n + "and more.", [T])
    check(f"D {n} spaces", cells(sb) == [("0.81", "UNet", "Dice", "0.81")] and time.perf_counter() - t0 < 1, cells(sb))

# --- E. size and time on a table-body sentence ---------------------------------------------------------------------
rnd = random.Random(1)
cols = ["Dice", "Sensitivity", "Specificity", "Precision", "Recall", "F1", "AUC", "IoU"]
big = [chunk(0, "We compare many networks.")]
for t in range(10):
    rows = [f"Net{t}x{r}" for r in range(15)]
    vals = [[f"0.{rnd.randint(80, 99)}" for _ in cols] for _ in rows]
    big.append(table(t + 1, f"Table {t + 1}: Results of setting {t}.", rows, cols, vals, page=t + 1))
    if t == 0:
        flat = " ".join(cols) + " " + " ".join(f"{rows[r]} " + " ".join(vals[r]) for r in range(15))
B._CACHE.clear()
t0 = time.perf_counter()
it = G.gate_paper({"results": flat}, big, "FULL_TEXT", [])["evidence"]["results"][0]
dt = time.perf_counter() - t0
size = len(json.dumps(it["structural_binding"]))
check("E table-body sentence: < 3 s, trace < 200 KB", dt < 3 and size < 200_000, f"{dt:.2f}s {size // 1024} KB "
      f"{it['structural_binding']['status']}")

print(f"\n{len(FAIL)} failing: {FAIL}")

if __name__ == "__main__":
    raise SystemExit(bool(FAIL))
