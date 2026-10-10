# BLOCKED

Latest status (2026-10-09): the context audit is complete; the binder remains unreleased.
Both subsequent repair attempts were reverted. S1=19 and S2=25 remain FAIL; S3's last
identity check passed. One current offline reproduction run confirms 11 failed / 21
passed on Python 3.10.18. Current evidence, expected outcomes and next action are in
[PROJECT_STATE.md](PROJECT_STATE.md). Entries below are historical blocker records.

## 2026-09-19 Phase 4 — Denominator reconciliation

**What I was doing:**
Starting Phase 4. The first step is to read Prakash's 90 human labels from
`experiments/document_evidence_pipeline/runs/phase3_composition/labelling_sheet.md`
and treat them as ground truth superseding my Phase 3 suggestions.

**What failed (exact error):**
No error was raised — the labels are not present. The worksheet is byte-for-byte as I
generated it:

    $ grep -c "YOUR LABEL:\*\* ________________" labelling_sheet.md
    90                          # all 90 fields still blank

    $ ls -l labelling_sheet.md
    -rw-r--r-- 58614 Sep 19 09:26 labelling_sheet.md     # mtime == my generation time

    $ git status --short
     M RESEARCH_DIRECTIVE.md    # my Step 0 append; nothing else modified

Every Phase 4 deliverable is label-dependent:
  A1/A2  raw agreement between your labels and mine        -> needs your labels
  B3     "build a MALFORMED detector from my labels"       -> needs your labels
  B4     detector precision/recall "against my 90 labels"  -> needs your labels
  B5     restate rates on the cleaned denominator          -> needs B3/B4
  C6/C7  extractor-wrong rate "on my labels"               -> needs your labels

There is no subset of this phase I can complete without them. Substituting my own
suggestions would present unvalidated machine labels as ground truth, which
RESEARCH_DIRECTIVE.md § "Labelling authority" forbids, so I did not do it.

**What I tried (list):**
1. `grep -c` on the blank-field pattern in `labelling_sheet.md` — 90 of 90 still blank.
2. `grep -n "YOUR LABEL:"` filtering out blanks — only hit is line 5, the instruction text.
3. `git status --short` — only `RESEARCH_DIRECTIVE.md` modified (Step 0). No new files.
4. `ls -lt runs/phase3_composition/` — no file newer than my 09:26 generation run.
5. `ls runs/ | grep -i phase` — no `phase4_denominator/`, no alternate worksheet.
6. Checked for a labels file under any other name in the output directory — only the
   superseded `labels.json` (my Phase 3 pilot suggestions) and my `suggested_labels.json`.

**What I need from you:**
Your 90 labels, in either form:

(a) Fill `YOUR LABEL:` in `runs/phase3_composition/labelling_sheet.md` in place and save, or

(b) Paste a flat list and I will parse it — one per line, id=LABEL:

        U01=MALFORMED
        U02=GENUINELY_UNNAMEABLE
        ...
        N01=FALSE_POSITIVE
        ...

    ids U01..U60 take one of:
        HAS_NAME_MISSED | NAMEABLE_INDIRECT | GENUINELY_UNNAMEABLE | MALFORMED
    ids N01..N30 take one of:
        CORRECT | FALSE_POSITIVE

Also needed, per section C5 of Phase 3: your confirmation or correction of the
machine-estimated ceiling (I estimated 30 of 60 usable; the worksheet has a
`YOUR CEILING CALL:` field per item, also unfilled).

Waiting.

## 2026-09-19 Phase 4 — Denominator reconciliation (SECOND occurrence)

**What I was doing:**
Re-attempting Phase 4 after being told "My labels are below / in the worksheet."

**What failed (exact error):**
No error. The labels are still not present, in either location.

    $ grep -c 'YOUR LABEL:\*\* ________________' runs/phase3_composition/labelling_sheet.md
    90                                  # 90 of 90 still blank
    $ ls -l runs/phase3_composition/labelling_sheet.md
    -rw-r--r-- 58614 Sep 19 09:26       # mtime == my generation time, unedited

    $ grep -c '^-> Y / N$' runs/phase3_label_assist/human_audit.md
    85                                  # 85 of 85 answer slots untouched
    $ ls -l runs/phase3_label_assist/human_audit.md
    -rw-r--r-- 42866 Sep 19 10:05       # mtime == my generation time, unedited

The message body contained three label lines and two literal ellipses:

    U01=Y
    U02=N
    ...
    N01=Y
    ...

That is 3 labels of 90. The "..." are placeholders, not data. I did not expand them.

**Received and recorded (not built upon):** U01=Y, U02=N, N01=Y.

Every Phase 4 deliverable needs materially more than 3 labels:
  A1   agreement vs framing_1 / framing_2 / the 6 provisional_N   -> needs all 90
  A2   split of the 26 disagreement vs 64 agreement items         -> needs all 90
  A3   how U52 was labelled                                       -> U52 NOT supplied
  B4   detector built from "my 60 Task A labels" + prec/recall    -> needs all 60
  B5   apply to 3,900 anchors                                     -> needs B4
  B6   restate every headline rate on the cleaned denominator     -> needs B4/B5
  C7   extractor-wrong rate from "my 30 Task B labels"            -> needs all 30
  C8   EVIDENCE_BINDING mass, "from my labels only"               -> needs C7

Building the B4 detector from my own earlier rules is explicitly excluded by the
brief ("The detector in B4 is built from my labels, not from your earlier rules").
Substituting my Phase 3 suggestions or the qwen judge outputs would present machine
labels as ground truth, which RESEARCH_DIRECTIVE.md section "Labelling authority"
forbids. I did neither.

**What I tried (list):**
1. grep for filled fields in labelling_sheet.md -- 90/90 blank.
2. grep for answered slots in human_audit.md -- 85/85 untouched, no marks.
3. mtime on both files -- unchanged since I generated them.
4. git status --short -- no new or modified file carrying labels.
5. Parsed the message body -- 3 explicit labels, 2 literal "..." placeholders.

**What I need from you:**
A ready-to-fill template is now at
runs/phase4_denominator/labels_template.txt -- 90 lines, 3 prefilled, 87 blank.
Fill the right-hand side and paste it back or save it. Allowed values:
  U01-U60: Y | N | UNCERTAIN        (Y = a real extracted fact)
  N01-N30: Y | N | UNCERTAIN        (Y = the metric name belongs to this value)

U52 matters specifically: it was the blind re-audit item for the 6 provisional-N.

Note: the four-way Phase 3 buckets (HAS_NAME_MISSED / NAMEABLE_INDIRECT /
GENUINELY_UNNAMEABLE / MALFORMED) were DEFERRED by the label-assist brief in favour
of the binary Y/N task. B4 asks for a MALFORMED detector. Binary Y/N is enough to
build and score it -- N is the malformed-or-not signal -- so I will use the binary
labels unless you want the four-way buckets instead. Say which.

Waiting.

## 2026-09-19 Phase 4 — Denominator reconciliation (THIRD occurrence — halting)

**What I was doing:** parsing the 90 labels, per instruction to echo the count and
stop if fewer than 90 parse.

**Parse result:** 0 of 90 parsed.
Unparseable line: the literal placeholder `<paste the 90 lines here>`.
On record from the previous message, unchanged: U01=Y, U02=N, N01=Y (3 of 90).

**What failed:** the labels are not in the message and not on disk.

    labels_template.txt      3 filled / 87 blank   mtime 10:15  (== my own write)
    labelling_sheet.md       90/90 blank           mtime 09:26  (== my generation)
    human_audit.md           85/85 untouched       mtime 10:05  (== my generation)
    find -newermt 10:06      only labels_template.txt, written by me

**What I tried:** parsed the message body; checked all three collection files for
filled fields; compared mtimes; searched for any file modified since the audit sheet
was written. Nothing carries labels.

**Halting per the directive.** RESEARCH_DIRECTIVE.md, Stop conditions: "Same error
encountered 3 times. Do not attempt a 4th fix." This is the third occurrence. I am
not attempting another route to obtaining the labels and will not restate the
request again.

**To resume:** send the 90 lines as message text, or fill
runs/phase4_denominator/labels_template.txt and save it. Phase 4 runs as briefed the
moment 90 parse.

## 2026-09-30 Phase — PDF table-cell implementation (after Stage B)

**What I was doing:** implementing ruled-PDF-table -> `table_cells` in
`src/evidence/represent.py` (`blocks_from_pdf`). The helper code is built and tested as a
scratchpad prototype first, so that it goes into production in one insertion.

**Which stop conditions fired (no test failed; nothing is broken):**
- `src/evidence/represent.py` has been edited twice this phase. Both edits are inert, so
  behaviour is identical to HEAD: one updated the docstring and added the `defaultdict` import,
  the other initialises the `captions` list. The remaining insertion (wiring plus helpers) would
  be the 3rd edit of that file.
- The prototype check script was run 4 times, each run after fixing a defect the previous run
  had surfaced.
- The phase has gone well past ~20 tool calls without a phase artifact.

**What I tried / found (prototype, all 30 physical PDFs):**
1. Text stream invariance holds. Blocks, text, ids, spans and types are identical to production;
   the extra keys appear only on table blocks.
2. Pairing bug found and fixed. A "table above caption" gap could go negative (-0.4 pt) and beat
   exact overlaps, which swapped P005 Tables 4 and 5. Gaps are now clamped at 0.
3. Five accepted grids were garbage:
   - rows stacked into one cell: P019 T1/T2, P027 T1;
   - wrapped-prose lines as rows: P020 T III;
   - a data row taken as the header: P024 T2.

   The binder matches numbers at token boundaries inside multi-value cells
   (src/evidence/gate.py:459-465), so a stacked cell would bind every method named in the
   merged label. I added three validation rules: `stacked_records`, `wrapped_text_rows` and
   `header_has_no_words`. Across all find_tables grids they fire only on garbage.
4. PyMuPDF sometimes reports the caption line as an "external header". That header is now
   ignored; P005 T1, T7 and T8 had headers made of caption fragments.
5. Caption continuation blocks between a caption and a table below it are appended. All 5 cases
   were checked and are genuine: P003 T2/T6, P008 T I/II, P023 T3.

**Result:** 158 table-typed blocks, 28 parsed, 643 cells. P003 Table 3 uses rule
`entity_column:1` ('S.no' is an index), and cell 92.3 has row "Proposed Method", column
"Dice Score (%)", page 6.

**What I need from you:** "proceed", to make the single final edit to represent.py (the 3rd this
phase), then:
- write the regression tests and run every suite;
- run P003 acceptance with the unchanged Stage B oracle functions;
- mine the 30 PDFs and run the post-fix evaluation.

There will be no 4th edit to represent.py: if the in-place tests expose a defect, I stop again.

## 2026-10-06 Phase 11

What I was doing: implementing Class B independent-value and complete-required-binding checks after
committing the scope, read-only diagnosis, validated Class A fix, and Class B failing tests.

What failed: both Python 3.10.18 and 3.13.6 report **98 passed, 2 failed**. Existing
`tests/test_binder_v2.py:165` expects a supported binding when another number occurs in no attached
cell; the candidate returns `partial_binding`. Existing `tests/test_binder_v2.py:177` expects
`not_a_table_claim` for a prose-only number; the candidate returns `not_bindable`.

What I tried: one Class B candidate patch after the committed 4-failure synthetic reproduction.
It prevents borrowing a later quantity, prefers explicit entity subjects, and broadens required
coverage to absent table values. All six new tests pass, but the two existing regressions trigger the
user's explicit STOP. No tests were changed, no further fix was attempted, and Part B was not started.

What I need from you: choose the required-value contract before resuming: retain the existing
value-matching rule and explicitly revise the new Class B scope/tests, or explicitly authorize
stricter coverage and updates to the affected old expectations. The candidate source remains
uncommitted; its exact diff and both runtime results are preserved under `docs/evaluation/evidence/`.
Full report: `docs/evaluation/phase_11_binder.md`; checkpoint: `docs/evaluation/checkpoints/phase_11_binder.md`.

### Class B resolution, 2026-10-06

The user explicitly chose Option 1 and authorized revising only the new Class B scope/tests.
The scope amendment was committed before code (`9a8fc9a`), tests revised with history preserved
(`cd53e13`), and the narrower fix committed (`176de61`). Table-absent values do not block a supported
bind and are not verified by it. Original tests remained unchanged; 102 focused checks passed in both
runtimes. Classes C and D then passed 117 and 125 focused checks respectively. The old rejected patch
is an archive, not an active uncommitted source change.

## 2026-10-06 Phase 11 A4 - current STOP

What I was doing: running the full authorized Python 3.10/3.13, legacy/v2 validation matrix after all
four implementation classes were committed (latest code `7f0cef3`).

What failed: the unchanged experiment unit suite under v2 reports **57 passed, 6 failed in each
runtime**. Failures in `experiments/document_evidence_pipeline/tests/test_pipeline_units.py` are the
own-cell nDCG@5 binding/return at line 262, cross-row abstention reason at 266, missing-column status
at 277, two generic performance-metrics statuses at 356/358, and generic count status at 368.

What passed: full pytest **226/226** in all four combinations; standalone pipeline **37/37** in all
four; experiment suite **63/63** under legacy in both runtimes; frozen binder regression **123/123**
under the legacy invocation in both runtimes. Explicit v2 regression invocation was not reached.

What I tried: one A4 validation matrix. No fix, test modification or additional baseline run followed
the failures. New S3, development measurement and Part B were not started. The latest user instruction
requires STOP if any pre-existing test fails, regardless of whether it is newly introduced.

What I need from you: authorization to diagnose and fix the six failures under the unchanged test
expectations before A4 can complete. No test waiver or frozen-file change is assumed. Details, raw
output locations and hashes are in `docs/evaluation/phase_11_binder.md` and
`docs/evaluation/evidence/phase11_validation.json`.

### Original six-failure STOP resolved, 2026-10-06

The user authorized the six fixes. Phase 10 baseline proved all six predated Phase 11.
Three failing-first general mechanisms were committed. All 138 focused checks pass
on both runtimes; the unchanged experiment suite passes 63/63 under v2 on 3.10.18.

## 2026-10-06 Phase 11 F5 - current STOP

What I was doing: the full A4 matrix after Class E implementation `6cc9b5c`.
What failed: frozen `src/evaluation/binder_10/regress.py:105` (B threshold alone) and
`:198` (B delta never binds), expected `not_a_table_claim`, actual `not_bindable`.
What passed: 3.10.18/legacy invocation, full pytest 239, standalone pipeline 37,
experiment 63; regression 121 passed / 2 failed. Regression internally selects v2.
What I tried: one F5 matrix, stopped at its first failed command. No further code
fix or rerun. The E2 quantity-scope check excludes threshold/delta mentions, causing
the status regression. Remaining combinations, S3, measurement and Part B not run.
What I need from you: continuation authorization to repair this non-equality status
boundary while preserving every original expectation. No test/evaluator edit or
waiver assumed. No final tag. Full evidence: phase11_a4_validation.json; current
report/checkpoint updated. No real LLM calls; offline guard proof is in the logs.

## 2026-10-07 Phase 11 - guard/R4 execution STOPs resolved; S1/S2 still fail

R3 6536d5c fixed the two frozen status expectations without changing existing tests.
The following R4 attempt stopped before launch because the offline guard scanned
subprocess.Popen's entire argument tuple, including the environment. One authorized
helper-only fix now inspects executable/argv and retains socket/LLM blocking.

All guard self-tests a-d passed. All 16 A4 combinations subsequently passed, including
regress.py:105 and :198 (not_a_table_claim). S3 passed 30/30 PDFs, 55 pairs/18 claims
identity, zero newline canary. The unchanged development-contaminated,
machine-assisted, unvalidated regression completed: S1 FAIL (19 gold flags); S2 FAIL
(25 lost gold/sweep occurrences). No new independent PDF audit or held-out evidence.
No further binder fixes, end-to-end run, cell-selection study or bottleneck work.

Publication status at report commit: local only, previous push rejected. One push
attempt follows; final session reply records the outcome. No tag exists at report time.
Full current report: docs/evaluation/phase_11_binder.md. Receipts: runs/phase11_binder/
a4_guard_selftest.json, a4_guard_resume_matrix.json, r5_results.json, r5_console.txt.
