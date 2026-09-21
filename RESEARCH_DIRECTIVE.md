# ResearchGPT — Research Execution Directive

## What we are doing
We are NOT improving ResearchGPT. We are measuring it to find out where it
fails. The deliverable is an error distribution by pipeline stage, not a
better pipeline.

Hypothesis: errors in a literature-review pipeline can be attributed to the
stage that produced them, and that attribution determines which fix is worth
making.

## The one rule
Do not assume the fix. Let the measured failure pick the fix.

## Phase gate protocol — READ THIS EVERY SESSION
Work proceeds in numbered phases. At the end of each phase you MUST:
1. Write the phase's named artifact to disk.
2. Print a <=15 line summary.
3. STOP. Do not begin the next phase. Wait for me to say "proceed".

Starting the next phase unprompted is a failure, even if the work is correct.

## Stop conditions — hard stops, no exceptions
Stop and report immediately when ANY of these fire:
- Same error encountered 3 times. Do not attempt a 4th fix.
- You have edited the same file 3 times within one phase.
- You have re-run the same script more than twice to "check if it works now."
- A task is taking more than ~20 tool calls without a written artifact.
- You are about to install a dependency not already in the project.
- You are about to create a file outside the paths listed in the current phase.
- You cannot find something and are about to guess its location or shape.

When a stop condition fires, append to /BLOCKED.md:
  ## <date> Phase <n>
  What I was doing:
  What failed (exact error):
  What I tried (list):
  What I need from you:
Then stop talking and wait.

## Anti-loop rules
- Never modify the evaluator after seeing evaluation results. That is
  optimizing the ruler. If the evaluator is wrong, stop and tell me why
  before touching it.
- Never re-run a full pipeline pass to verify a change. Write a 5-line test
  against a single fixture instead.
- If a command outputs more than 200 lines, summarize it. Do not paste it.
- Do not refactor. Do not rename. Do not clean up. Do not add type hints,
  docstrings or logging to existing code unless the phase asks for it.
- If you find a bug unrelated to the current phase, write it to /FINDINGS.md
  and keep going. Do not fix it.

## Evidence rules
- Every factual claim about this codebase cites `path/to/file.py:LINE`.
- Never report a step as done without naming the artifact path it produced.
- If you did not read a file, say so. Do not infer its contents from its name.
- Never invent a schema field. If the schema lacks something, that is a
  finding, not a gap to fill.

## Forbidden in all phases unless I explicitly ask
UI work, authentication, Supabase, deployment, Docker, multi-agent anything,
swapping ChromaDB, swapping Qwen/Ollama, swapping BGE-M3, adding GROBID,
adding BM25, adding SPECTER2, adding a reranker, adding OCR, expanding the
corpus, new vector DB, new parser, new frontend, prompt "improvements",
rewriting run_pipeline.py.

GROBID, BM25, SPECTER2, rerankers and OCR are CANDIDATE INTERVENTIONS to be
selected by measurement in Phase 8. They are not solutions. Do not add them
because the literature mentions them.

## Terminology — do not blur these
- representation failure: the info was lost by the parser
- retrieval failure: the info exists in the store but did not reach the model
- extraction failure: the info reached the model and the model got it wrong
- evidence-binding failure: the value is right, the cited location is wrong
- unsupported generation: the info is not in the source at all

Never call any of these "hallucination" without ruling out the first three.
LaTeX and JATS are REFERENCE REPRESENTATIONS for comparison, not absolute
ground truth. They contain macros, generated tables and author errors.

## Reporting format at every stop
STATUS: <done | blocked>
ARTIFACT: <path, or none>
FOUND: <3-6 bullets, each with file:line>
UNCERTAIN: <what you are not sure about>
NEXT PHASE WOULD BE: <one line>
Awaiting "proceed".

## Attribution rule
Attribute every failure to the EARLIEST stage at which the required evidence
becomes unavailable or incorrect. Never infer the stage from the final model
error alone — attribution rests on the identity and availability of the correct
evidence at each stage (chunk id, retrieval rank, whether it entered the
delivered set). "The answer was wrong" is not evidence of where it went wrong.

## Two separate questions, two separate fields
Never merge these into one enum.
  outcome:     SUPPORTED | WRONG | UNSUPPORTED | UNCERTAIN
  failed_at:   ACQUISITION | REPRESENTATION | EVIDENCE_SELECTION |
               EXTRACTION | EVIDENCE_BINDING | NOT_DIAGNOSABLE

EVIDENCE_SELECTION always carries a subcategory — query | ranking | budget |
policy. Do not use the bare parent. Phase 2 showed the retriever ranks
correctly (R@10 0.940) while the selection policy discards the result
(delivery 0.071); collapsing these destroys that finding.

NOT_DIAGNOSABLE carries a reason — artifacts_missing | evidence_ambiguous.

## Verification discipline
Every automatic decision records verification_method (exact | normalized |
semantic | structural | manual) and verification_confidence (high | medium |
low). Report coverage separately from accuracy. Never emit a single pooled
accuracy number.

## Kappa commitment — decided in advance, not after seeing results
We report Cohen's kappa. Therefore every category we report kappa for gets
>=50 human-labelled items. Categories under 50 are reported as raw agreement
and labelled "pilot, n<50". Fixed now; does not change once the distribution
is visible.

## Labelling authority
Human labels are Prakash's to make. You may emit suggested labels, always
marked "machine-assisted, unvalidated". Never present your own labels as
ground truth or as the basis of a reported rate without that marking.

## Product mode (from Phase 7)
The measurement programme (Phases 0-6) is closed. From Phase 7 the goal is a
product that runs correctly on machines other than the development machine.
Phase gates, stop conditions, anti-loop rules and evidence rules apply
unchanged.

In product mode a phase may permit edits to src/, configs/ and root files —
only the edits that phase lists. Everything on the forbidden list stays
forbidden unless a phase names it.

Any edit to src/ must leave behaviour on the development machine (GPU and
Ollama present, same config) unchanged unless the phase says otherwise.
Verify with deterministic checks — resolved config values, resolved device —
not with a full pipeline run and not by diffing LLM output.

Frozen results: n_results=50 at src/summarization/retrieval_aware.py
(commit 2c7d0a9) stays in every branch and every merge. The malformed
fraction is 31.0% (1,209 / 3,900), cleaned n = 2,691; Phase 4's 29.9%
figure is superseded per FINDINGS.md.
