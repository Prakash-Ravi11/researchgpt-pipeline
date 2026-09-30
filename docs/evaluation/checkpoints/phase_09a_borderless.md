# Phase 09A — Borderless-table backend behind a default-off flag

## Objective
Add a Docling + TATR consensus backend for tables rejected as `no_ruled_table_beside_caption`, behind
`borderless_policy` (default `off`). Validate it on the existing gold set, and enable it only if the
pre-registered P1–P4 pass.

## Inputs
- `src/evaluation/bottleneck_diagnosis/postfix_claim_cell_gold.json`: 55 pairs / 18 claims / 12 papers;
  machine-assisted, not human-validated.
- `postfix_claim_cell_report.md` and `postfix_binder_oracle.json`: phase 08 failure categories.
- The hash-pinned PDFs (`pdf_identity_manifest_v2.csv`).
- Pre-registration: `src/evaluation/borderless_09a/PREREG_09A.md`.

## Work Performed
(in progress)
- Target set derived: **10 tables / 11 claims**, matching the brief.
- Branch `exp/phase09a-borderless` created from `30fc85d` with two commits:
  - `4d3c183`: bottleneck_diagnosis;
  - `797a922`: the phase 04–08 baseline, which is the "current HEAD" for flag-off identity.
- Pre-registration committed before any run.

## Results
(pending)

## Evidence
(pending: `src/evaluation/borderless_09a/`)

## Decisions
- "Current HEAD" = `797a922`: the phase 04 `represent.py` state on which the 55 pairs were evaluated.
- The dependency installs into `.venv-09a` are explicitly authorised by the phase 09A brief. This is an
  exception to the directive's "new dependency" stop condition, and it is recorded here.

## Changes
- Commits so far: `4d3c183`, `797a922`, then the pre-registration commit.

## Temporary Files
(none yet)

## Cleanup
(pending)

## Current State
In progress: Step 0 done.

## Next Step
Create `.venv-09a`, then the Step 1 oracle ceiling, then the backends.

## Do Not Redo
The target-set derivation (10/11) and the pre-registration.

## Reproduction
(pending)
