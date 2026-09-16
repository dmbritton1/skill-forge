# E16: two more author-mode traps

**Status:** written 2026-09-16, before any E16 session ran. Every criterion
below is fixed before the data it governs. The pre-flight (section 2) has
already run — it spends no session — and both candidates passed it.

## Why

Trap supply is the binding constraint on every experiment that needs more than
one task. It is less binding than the handoff says, and the correction matters
for what this screen is for.

**`docs/session-handoff.md` §3.8 is stale.** It says the bench has one usable
trap. It has two:

| task | control | treatment |
| --- | --- | --- |
| `sf-author-fingerprint-preexisting` | **0 of 25** lifetime | pilot 5/6, E5 hot 5/6 |
| `sf-author-verdict-from` | **0 of 23** lifetime | E15 variant drafts **18/18** |

E13 §6 read trap C (`verdict_from`) as serving neither of its two traps,
because its own drafts pooled 7/15 against a pre-registered half. E15 then
resolved that task 18/18 with drafts written under three new distiller rules,
against 0/9 for E13's drafts and 0/3 control. A task with a zero floor that a
good skill takes to ceiling is a working trap; what E13 measured was its
drafts, not the task. Counts above are from `bench/results.jsonl`, over every
control row whose `session_ok` is true, including the rows excluded from their
own batches.

Two is still not many, and both are author-mode tasks against `scripts/`
review findings, so they share a failure mode. E16 screens two more.

## 1. Candidates

`bench/trap_candidates.py` ranks the 48 post-cutoff fix commits that touch both
`scripts/` and `tests/` by author-mode shape. Its validity footer still holds:
the two known-good traps rank 5 (`22ddf37`) and 10 (`ab4acfe`) of 48.

Five commits are spent — `22ddf37` and `ab4acfe` (the known traps) and
`c0d7d88`, `521f609`, `06173b0` (E13's C, D and E). E13 §1 hand-reviewed and
dropped fourteen more with reasons; those reasons were re-checked against the
diffs and all of them hold, so none is revisited.

Of what is left, the binding shape is narrower than the fitness score sees: the
fix must change **one top-level function that already existed at the parent
carrying a docstring**, because `stub_cmd` blanks that body and the session
authors against that docstring. Exactly two commits clear it.

| cand | fix | function | the trap | family |
| --- | --- | --- | --- | --- |
| F | `ea4c47f` | `reconcile.read_markers` | `json.loads` raises `RecursionError` on a deeply nested line, not a `ValueError`. A narrow `except` on untrusted input lets it escape, and the docstring's promise — "bad lines are skipped rather than raising" — silently stops holding | Untrusted-input parsing (new) |
| G | `58ce279` | `ledger.event_totals` | SQL `GROUP BY outcome` returns NULL and `''` as separate rows. Both map to the `unknown` bucket, and assigning instead of adding makes the second clobber the first | Fold-into-a-default (new) |

Both are hidden inferences about a library's behaviour, not facts about this
codebase and not added requirements — the two reasons E13 dropped most of its
field on. `RecursionError` is confirmed on the interpreter the bench runs
(`json.loads("[" * 20000)`, Python 3.9.6): it is not a `ValueError`.

### 1.1 The rest of the field, and the next in line

Everything else fails the shape test for one of these reasons, recorded so the
next session does not re-derive it:

- **The fixed function was created by the fix**, so author mode has nothing to
  stub: `5763117` (`draft.evidence_window`, extracted from `main()`). Its trap —
  a second-granularity stamp compared closed against microsecond entries — is a
  good one and stays unreachable in this shape.
- **The fix adds a key or parameter the contract would have to name**, which
  gives it away: `cc9859a` and `1ba440b` (new dict keys on `usage_for` and
  `event_totals`), `065576b`, `0e726fc` (a new SQL view column).
- **The change is not in a function body**: `db19377` and `2063f3a` (module
  constants), `b25a9cb`, `2a4a15a`, `b0110ae`, `7a1d3ac`, `8bc7253` (call sites
  inside large orchestration functions).
- **Several unrelated changes in one commit**: `f8a4738`, `171a63e`, `9b03dc1`,
  `1fced95`, `0aaa51d`, `fa870f1`, `b030125`, `7550148`, `56b4cfd`.
- **An added requirement**: `3095587`, `e4ff418`.

**Next in line if F or G is rejected:** `7a1d3ac` (`library.cmd_delete`, no
docstring at the parent, so it would need a fresh one-line contract as E13's
trap E did). It is named here rather than screened because E13's only
fresh-contract candidate was rejected at 6/6, and 6 sessions are better spent
after this screen reads than beside it.

## 2. Building the tasks

Each candidate becomes an **author task**, built exactly as
`sf-author-fingerprint-preexisting` is: the clone sits at the fix's parent, a
stub replaces the target function with a body that raises `NotImplementedError`
under **the parent's own docstring, verbatim**, and the fix commit's test file
is applied after the session ends.

| task | stubbed | docstring |
| --- | --- | --- |
| `sf-author-read-markers` | `read_markers(cwd)` | The parent's own, verbatim |
| `sf-author-event-totals` | `event_totals(*, path=None)` | The parent's own, verbatim |

Neither task needs the fresh-contract departure E13's trap E made. The prompt
is the existing author template verbatim, with the file, the signature and the
test command substituted.

### 2.1 The graded tests are decided mechanically

`bench/e16_preflight.py` reuses E13's method by importing
`bench/e13_preflight.py` rather than copying it. Each candidate's fix-commit
test file runs three ways against the parent: **(1)** with the stub, **(2)**
with the parent's original function — the historical bug — and **(3)** with the
fix's changed definitions transplanted in. **The graded set is every test that
fails in run 1 and passes in run 3.** A task is valid only if run 2 fails at
least one graded test encoding the fix, passes every other graded test, and run
3 passes all of them.

**One rule differs from E13, and this is the only departure.** E13 proved the
tests catch the historical bug using the tests the fix **added**. Candidate F's
fix records its bug by adding a line to an **existing** test, so its added set
is empty and E13's rules would call it invalid for a reason that says nothing
about the trap. E16 uses the tests the fix **added or changed**: a test whose
body the fix rewrote encodes the fixed behaviour exactly as well as a new one.

Editing a docstring, or dropping a graded test, to make a run pass is not
allowed. Neither candidate needed a `hidden_patch_cmd`.

**Pre-flight result (already run, 0 sessions):**

| cand | stub | original | fix | graded | the fix's own test |
| --- | --- | --- | --- | --- | --- |
| F | 11 pass / 64 fail | 74 / 1 | 75 / 0 | **64** | `test_read_markers_skips_junk_without_losing_good_lines` (changed) |
| G | 60 pass / 5 fail | 64 / 1 | 65 / 0 | **5** | `test_event_totals_sums_null_and_empty_outcome_into_unknown` (added) |

Both are **VALID**. In both, the historical bug fails **exactly one** graded
test — the same shape E13's trap C showed. Section 3.3 turns that into a rule.

### 2.2 The grading command

`bench/run.py::score` counts only `PASS <name>` lines. `tests/test_reconcile.py`
aborts at the first failure, so F grades through
`bench/run_named_tests.py` over its 64 graded tests, as E13's D did.
`tests/test_ledger.py` catches each test's failure and uses its own runner.

## 3. The control screen

E11's and E13's rules, so the three screens are comparable, with the pacing
changed under E15 amendment 4.

### 3.1 Composition

- **6 control sessions** per candidate, no skill installed in any cell.
- **A same-batch reference:** 3 control sessions on
  `sf-author-fingerprint-preexisting` (0 of 25 lifetime).
- 15 sessions, plus one allowance probe and at most 6 repeats.

### 3.2 Order, and pausing at the session limit

E13 ran each cell as one block and **postponed** a whole screen at the session
limit. E15 amendment 4 replaced that with pause-and-resume, because a batch
longer than one window can never finish if it must be re-run whole. E16 adopts
it, and adds interleaving, because a window boundary inside a single block
would confound that cell with the environment:

- **Three interleaved rounds**, each opening with the reference:
  `R, F, G, F, G` × 3. `bench/e16_screen_read.py --order` is the authority.
- A **failed session** (`session_ok` false, at the limit or otherwise) never
  counts, does not take its slot, and is re-run in its place. It does not use a
  repeat. The limit cuts sessions off mid-run, so such a row is never read as a
  result.
- At the session limit `bench/e16_screen.sh` waits for the reset and goes on.
  There is no cap on windows. After 3 failed sessions in a row, or 3 runs that
  write no row, it stops, and `--resume <SCREEN_START>` continues the **same**
  batch from the rows already written.
- **Batches are never stitched.** Every row must share one CLI version, model
  and plugin commit. The script stops before a session if either moved, and the
  reader reports mixed rows as `mixed` — not readable.
- Repeats are at most 6 finished sessions after the order, and exist only for
  rows that were written but do not count (a non-`clean` audit).

### 3.3 Admission: a zero floor the trap produced

E13 admitted on `0 of 6` alone. That is necessary and, for candidate F, not
sufficient: F grades 64 tests, so a session that never implemented the contract
at all also reads 0/6, and that floor would say nothing about `RecursionError`.
Every unresolved control row is attributed from its `per_test`:

- **`trap`** — the only graded test it failed is the historical bug's own
  (§2.1's table);
- **`wider`** — anything else failed too.

**Pre-registered verdicts, decided before any row exists:**

- **Rejected:** any valid control row resolved. One is enough.
- **Admitted:** 0 of 6 resolved **and** more than half the cell (at least 4 of
  6) attributed `trap`.
- **Floor not attributable:** 0 of 6 but 3 or fewer `trap` rows. Neither
  admitted nor rejected — the floor is task difficulty, and the candidate goes
  back to the list with that written down. The 4-of-6 line is a bare majority,
  chosen here because it is arbitrary and therefore must be fixed in advance.

### 3.4 The reference is read first

If the reference resolves even once the batch is **void** and no candidate is
read at all — E10's break was caught only because a second task's control ran
in the same batch. While the reference is incomplete, candidate cells are
counted for the driver's bookkeeping but carry **no verdict**.

### 3.5 Exclusions

A row the sandbox audit rejects (`bench/audit.py::counts`) does not count
toward any cell and is replaced by a repeat. A failed session is handled by
§3.2 and is not an exclusion.

## 4. What follows the screen

- **Every admitted candidate is distilled**, the way E13 §5 did it: a repair
  task on the same bug, both distillers with the novelty gate off, 3 draws
  each, a draft counting only if its repair resolved. Under E15's result the
  skills distiller now carries the three writing rules, so the drafts are not
  E13's drafts and no E13 probe number transfers to them.
- **Nothing beyond the screen is pre-registered here.** Distillation and any
  probe get their own spec, written before they run.
- **If nothing is admitted**, it is back to §1.1's next in line.

## 5. Threats

1. **A fresh model may simply be right.** Both contracts state the property the
   historical bug broke. A session that writes `except Exception` or `+=`
   without ever reasoning about `RecursionError` or SQL's NULL group resolves
   the task, and the candidate is rejected at 6/6 — exactly what happened to
   E13's D and E. Expected attrition, not a defect.
2. **F's graded set is 64 tests wide.** §3.3 exists for this and is the
   mitigation; it does not remove the risk that F floors for mixed reasons.
3. **G's docstring is thinner than F's on the return shape.** It names the
   `unknown` bucket but not the `by_type` / `by_detection` keys, which the
   session must infer from the call sites in `scripts/stats.py`. If that
   inference is what fails, §3.3 reads it as `wider`.
4. **`58ce279` closed six review findings.** Only one touches a function body
   in `scripts/`; the other `scripts/` change is a module docstring in
   `stats.py`, which the stub does not touch and nothing grades. Stated, not a
   defect.
5. **Two new traps would still all be `scripts/` review findings stubbed from a
   docstring.** A screen cannot tell a trap that generalises from one that only
   works in this shape. Nothing here addresses that.

## 6. What this cannot answer

Whether an admitted candidate is a *useful* trap — whether a distilled skill
moves it — is not this screen. E13's C was admitted at 0/6 and took two more
experiments to produce a skill that worked on it. The screen buys headroom and
nothing else.
