"""All precision-lens reproductions (synthetic chunks only). Each row: tag, claim, v2 result, legacy result.
Run from the repo root:  .venv/Scripts/python.exe -B <this file>"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from h import B, bind, chunk, table  # noqa: E402

X = chunk(0, "x")
T = table
TR = lambda: T(1, "Table 1: Segmentation results on the test set.", ["UNet", "Ours"], ["Dice", "HD95 (mm)"],
               [["0.81", "4.2"], ["0.87", "3.1"]])
TB = lambda: T(1, "Table 1: Dice and HD95 of the compared methods.", ["Dice", "HD95"], ["UNet", "VNet", "FetalNet"],
               [["0.81", "0.79", "0.88"], ["4.2", "5.1", "3.0"]])
FETAL = chunk(0, "FetalNet is a new network for fetal MRI.")
R = [
    # 1 qualifier conflict read only in the comma-cut window, not the clause
    ("QUAL2", "On BraTS, UNet obtains a Dice of 0.81.",
     [X, T(3, "Table 3: Results per dataset.", ["UNet", "Ours"], ["BraTS / Dice", "ISLES / Dice"], [["0.79", "0.81"], ["0.89", "0.88"]])]),
    ("QUAL1", "On small lesions, our method achieves a Dice of 0.85.",
     [X, T(4, "Table 4: Dice by lesion size.", ["Small", "Large", "All"], ["UNet", "Ours"], [["0.70", "0.82"], ["0.80", "0.85"], ["0.75", "0.84"]])]),
    ("HIER1", "Ours reaches a Dice of 0.88 on ISLES and 0.85 on BraTS.",
     [X, T(3, "Table 3: Results per dataset.", ["Ours", "VNet"], ["BraTS / Dice", "BraTS / HD95", "ISLES / Dice"], [["0.89", "0.85", "0.88"], ["0.86", "1.20", "0.84"]])]),
    # 2 subject link from anywhere in the sentence; own refs never conflict
    ("A1", "Our method achieves a Dice of 0.85, outperforming UNet and VNet.",
     [X, T(1, "Table 1: Segmentation results on the test set.", ["UNet", "VNet", "Ours"], ["Dice"], [["0.81"], ["0.85"], ["0.87"]])]),
    ("C3", "The baseline reaches a Dice of 0.85, below our method.",
     [X, T(3, "Table 3: Results per dataset.", ["Ours", "UNet"], ["BraTS / Dice", "ISLES / Dice"], [["0.89", "0.85"], ["0.87", "0.80"]])]),
    # 3 entity axis
    ("B1", "On the external set, our method reaches a Dice of 0.81.", [FETAL, TB()]),
    ("B3", "For FetalNet, the Dice is 0.81.", [FETAL, TB()]),
    ("FLIP2", "Our method achieves a Dice of 0.81.",
     [X, T(1, "Table 1: Dice of the segmentation methods.", ["UNet", "FetalNet"], ["Dice", "p (vs. proposed)"], [["0.81", "0.01"], ["0.87", None]])]),
    ("DECL3", "Our method achieves a DSC of 0.81.",
     [chunk(0, "Overlap is measured with a metric called DSC."),
      T(1, "Table 1: DSC and HD95 results.", ["UNet", "FetalNet"], ["DSC", "HD95"], [["0.81", "4.2"], ["0.87", "3.1"]])]),
    # 4 caption word as the quantity link
    ("F1", "Ours reaches an HD95 of 0.95 on BraTS.", [X, TR(), T(10, "Table 10: Results on BraTS.", ["Ours"], ["Dice"], [["0.95"]], page=10)]),
    # 5 multi-metric cells
    ("PART1", "Smith et al. (2020) reported an IoU of 0.85.",
     [X, T(4, "Table 4: Prior work, Dice and IoU.", ["Smith et al. (2020)", "Lee et al. (2021)"], ["Results"], [["Dice: 0.85"], ["IoU: 0.80"]])]),
    ("PART2", "Smith et al. (2020) reported an HD95 of 85.1.",
     [X, T(4, "Table 4: Prior work.", ["Smith et al. (2020)"], ["Results"], [["Dice (%): 85.1, HD95: 4.2"]])]),
    ("PART3", "Smith et al. (2020) reported an IoU of 0.85.",
     [X, T(4, "Table 4: Prior work.", ["Smith et al. (2020)"], ["Results"], [["Dice 0.85 / IoU 0.74"]])]),
    ("SLASH1", "Ours reaches an IoU of 0.87.",
     [X, T(1, "Table 1: Segmentation results.", ["UNet", "Ours"], ["Dice / IoU"], [["0.81 / 0.70"], ["0.87 / 0.78"]])]),
    # 6 spurious own-method declarations
    ("D1", "Our method achieves a Dice of 0.81.", [chunk(0, "Ronneberger et al. introduced an architecture called UNet."), TR()]),
    ("D2", "Our method achieves a Dice of 0.81.", [chunk(0, "We present a comparison against UNet on the test set."), TR()]),
    # 7 count channel ignores the counted noun
    ("C1", "The training set contains 15 subjects.",
     [X, T(6, "Table 6: Summary of the data used.", ["Training", "Testing"], ["Number of subjects", "Number of scans"], [["12", "15"], ["18", "30"]])]),
    ("COUNT2", "Ours improves by 12 percentage points.",
     [X, T(1, "Table 1: Results.", ["UNet", "Ours"], ["N", "Accuracy (%)"], [["20", "81"], ["12", "93"]])]),
    # 8 bracketed qualifiers discarded
    ("Q1", "UNet (scratch) obtains a Dice of 0.81.",
     [X, T(1, "Table 1: Segmentation results.", ["UNet (pretrained)", "UNet (scratch)", "Ours"], ["Dice"], [["0.81"], ["0.79"], ["0.87"]])]),
    ("OWNV", "Our method achieves a Dice of 0.85.",
     [X, T(1, "Table 1: Results.", ["UNet", "Ours (w/o CRF)", "Ours"], ["Dice"], [["0.81"], ["0.85"], ["0.87"]])]),
    # 9 labels differing only in symbols / a longer unlisted name
    ("S1", "DeepLabv3+ achieves a Dice of 0.85.",
     [X, T(1, "Table 1: Segmentation results.", ["DeepLabv3", "DeepLabv3+", "Ours"], ["Dice"], [["0.85"], ["0.86"], ["0.87"]])]),
    ("SUF1", "Swin UNETR achieves a Dice of 0.81.", [X, T(1, "Table 1: Segmentation results.", ["UNETR", "Ours"], ["Dice"], [["0.81"], ["0.87"]])]),
    # 10 comparison roles
    ("ROLE1", "Ours outperforms UNet in Dice (0.87 vs 0.80).",
     [X, T(3, "Table 3: Results per dataset.", ["Ours", "UNet"], ["BraTS / Dice", "ISLES / Dice"], [["0.89", "0.81"], ["0.87", "0.80"]])]),
    ("ROLE3", "Compared with UNet, Ours achieves a Dice of 0.87 vs 0.80.",
     [X, T(3, "Table 3: Results per dataset.", ["Ours", "UNet"], ["BraTS / Dice", "ISLES / Dice"], [["0.87", "0.80"], ["0.82", "0.78"]])]),
    # 11 claim qualifiers that belong to another table (or none) never count against a cell
    ("DOM1", "Our method achieves a Dice of 0.923 on CSF.",
     [X, T(1, "Table 1: Segmentation results on the test set.", ["UNet", "Ours"], ["Dice"], [["0.81"], ["0.923"]]),
      T(2, "Table 2: Per-structure results.", ["CSF", "WM"], ["UNet", "Ours"], [["0.90", "0.923"], ["0.88", "0.91"]], page=2)]),
    ("CTX1", "Ours achieves a Dice of 0.95 on BraTS.", [X, T(11, "Table 11: Results on ISLES.", ["Ours"], ["Dice"], [["0.95"]])]),
    # 12 value parsing
    ("THOUS1", "The training set contains 1,500 images.",
     [X, T(6, "Table 6: Summary of the data used.", ["Training", "Testing"], ["Number of images"], [["500"], ["200"]])]),
    ("SIGN1", "Age showed a Pearson r of -0.35 with the volume.",
     [X, T(1, "Table 1: Correlation with the volume.", ["Age", "Weight"], ["Pearson r"], [["0.35"], ["0.12"]])]),
    # minor paths
    ("RANGE1", "The training cohort had a mean gestational age of 21 weeks.",
     [X, T(6, "Table 6: Summary of the data used.", ["Training", "Testing"], ["Gestational age (weeks)"], [["21-38"], ["22-35"]])]),
    ("PCT1", "Ours improves the Dice by 0.95% on BraTS.", [X, T(10, "Table 10: Results on BraTS.", ["Ours"], ["Dice"], [["0.95"]])]),
    ("TM1", "As shown in Table 2, ours reaches a Dice of 0.91.",
     [X, T(1, "Segmentation results.", ["Ours"], ["Dice"], [["0.91"]]), T(2, "Table 2: Results on ISLES.", ["Ours"], ["Dice"], [["0.93"]], page=2)]),
    ("AL1", "With deep learning, the network reaches a Dice of 0.85.",
     [chunk(0, "We use a base learning rate of 0.001."), T(1, "Table 1: Results.", ["Base", "Ours"], ["Dice"], [["0.85"], ["0.87"]])]),
    ("THR2", "Ours achieves a Dice above 0.87 vs 0.81 for UNet.", [X, TR()]),
    ("PROP1", "VNet with the proposed loss reaches a Dice of 0.87.", [X, TR()]),
]


def res(pol, claim, ch):
    os.environ["RGPT_BINDER_POLICY"] = pol
    sb = bind(claim, ch)
    if sb["status"] != "bound":
        return sb["status"]
    if sb.get("bindings"):
        return "BOUND " + "; ".join(f"{b['number']}->({b['cell']['row']} | {b['cell']['col']} | {b['cell']['value']})"
                                    for b in sb["bindings"])
    return f"BOUND ({sb['cell']['row']} | {sb['cell']['col']} | {sb['cell']['value']})"


n = 0
for tag, claim, ch in R:
    v2, lg = res("v2", claim, ch), res("legacy", claim, ch)
    n += v2.startswith("BOUND")
    print(f"{tag:7s} {claim}\n        v2:     {v2}\n        legacy: {lg}")
print(f"\n{n}/{len(R)} reproductions bound by v2")
