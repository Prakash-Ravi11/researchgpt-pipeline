# Phase 11: E2 non-equality status regression mechanism

Read-only diagnosis at checkpoint `5303405`, before this resumption's tests or fix.
The responsible change is `198c9225d506b2eee04e3ac2df93e605ed18da15` (E2).

In `src/evidence/binder_v2.py`, `_bind_v2` skips threshold and delta mentions before
candidate construction (lines 1151-1153). A claim containing only these mentions
therefore leaves `required=0` and `any_cand=False`: its numbers are not absolute
cell-value assertions, even if the same numeric token occurs in a table.

The E2 branch at lines 1206-1218 handles `not required`. Its `quantity_scoped`
generator excludes every threshold/delta mention a second time (line 1213), so
`any(...)` is false for these claims. Line 1215 consequently returns
`not_bindable`. Before E2, this branch returned `not_a_table_claim` when no absolute
value candidate had been considered. Thus E2 conflates an explicitly non-equality
claim with an equality claim whose quantity is absent from the table.

| Frozen assertion | Expected status | Actual status at this checkpoint |
| --- | --- | --- |
| `src/evaluation/binder_10/regress.py:105`: `B threshold alone` | `not_a_table_claim` | `not_bindable` |
| `src/evaluation/binder_10/regress.py:198`: `B delta never binds` | `not_a_table_claim` | `not_bindable` |

The gate's documented binding decision (`src/evidence/gate.py:390-430`) distinguishes
unrepresented quantities (`not_bindable`) from claims that do not assert an
attached cell value (`not_a_table_claim`). Binder v2's frozen threshold/delta tests
make the non-equality boundary explicit. Its mixed threshold-plus-comparator
expectations (`regress.py:104-107`) also distinguish an independent equality
mention from a threshold-only claim. Neither abstention status means a bound cell.

Absent-metric and generic-count equality claims remain separate: they have an
ordinary value mention but no supported table quantity. Their original
`not_bindable` expectations must remain unchanged. This diagnosis records only
the mechanism and existing contracts; it changes no implementation or expectation.
