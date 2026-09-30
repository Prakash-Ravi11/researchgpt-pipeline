# BLOCKED

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
