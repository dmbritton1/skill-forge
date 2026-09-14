# E13: three new author-mode traps

**Status:** design agreed in brainstorming on 2026-09-13, and written before any
E13 session ran. Every criterion below is fixed before the data it governs.

## Why

The bench has one usable trap, `fingerprint_preexisting`, whose control has
resolved 0 times in 21. E11 rejected both repair-mode candidates, and E10
retired `response_text`.

The tokenizer fix (`9cbb472`) is confirmed through the real install-and-inject
path (`bench/real_path_check.py`, 4 of 4). But no current task can show whether
the fix improves outcomes. The only author task whose delivery it changes is
already at ceiling, and the only task with headroom delivered correctly before
the fix too.

E13 has two goals:

- **Trap 1:** a second working author-mode trap, to unblock any experiment that
  needs two.
- **Trap 2:** a trap whose delivered skill the tokenizer fix changes, so that a
  session batch can measure whether the fix improves outcomes.

## 1. Candidates

`bench/trap_candidates.py` ranked 48 post-cutoff fix commits by author-mode
shape, and 19 of them were reviewed by hand. Three survive.

| trap | fix | function | the trap | family |
| --- | --- | --- | --- | --- |
| C | `c0d7d88` | `validate.verdict_from` | Exact substring matching rejects a quote that a critic re-wrapped across lines. The 12-character floor must also be measured on the raw span | Trap A (formatting defeats matching) |
| D | `521f609` | `draft.transcript_slice` | "Nothing in the window" is treated like "no timestamps", so it returns an unrelated tail | Near trap B (absence) |
| E | `06173b0` | `save_skill.store_dir`, `save_skill.native_dir` | A relative `"."` project root is compared against an absolute home path, so re-saving a skill collides with itself | Path identity (new) |

The dropped candidates, and why:

- **`2f67782` (`unattemptable`), `f4927ec`:** the fix changed a requirement. A
  contract-only docstring would either leave out what the tests grade or give the
  fix away.
- **`065576b`:** the fix adds a parameter that the contract would have to name.
- **`5763117`, `0c93439`:** the fixed function was created by the fix, so author
  mode has nothing to stub.
- **`ba408de`, `2e91e1c`, `ee009b5`, `fdb7c61`:** each bundles several unrelated
  changes. `ba408de` and `2e91e1c` also depend on timing-sensitive tests.
- **`26e8f56`:** the answer is observable during the session, because any failing
  Bash call shows the model the result shape.
- **`6770514`, `2b92a7e`, `72009d2`, `c8921d3`:** a fact about this codebase, or an
  added requirement, rather than a hidden inference. `c8921d3`'s core fact
  (argparse's `--help` writes to stdout) is worth isolating as a trap later.

All three survivors are unscreened, and E11 rejected both of its candidates at
the control screen, so some attrition is expected.

## 2. Building the tasks

Each candidate becomes an **author task**, built the same way as
`sf-author-fingerprint-preexisting`:

- the clone sits at the fix's parent commit;
- a stub script replaces the target function or functions with a body that raises
  `NotImplementedError`, under a docstring that states only the contract;
- the fix commit's test file is applied after the session ends.

| task | stubbed | docstring |
| --- | --- | --- |
| `sf-author-verdict-from` | `verdict_from` | The parent's own, verbatim |
| `sf-author-transcript-slice` | `transcript_slice` | The parent's own, verbatim |
| `sf-author-store-dir` | `store_dir`, `native_dir` | None existed at the parent, so a one-line contract naming the directory layout, silent on path resolution. This departs from the historical condition and is listed as a threat (§11) |

The prompt reuses the existing author template verbatim, with the file, the
function signature and the test command substituted:

> `<file>` has a function `<signature>` whose body raises NotImplementedError.
> Read its docstring for the contract and implement it. Do not change its
> signature, and do not modify anything under tests/. When you are done, run
> `<test command>` and make sure you have not broken any test that was passing
> before your change.

For E, "a function … whose body raises" becomes "functions … whose bodies
raise", and "its docstring" becomes "their docstrings".

### 2.1 The graded tests are decided mechanically

A zero-session pre-flight runs each task's fix-commit test file against the
parent's code, three times over:

1. **With the stub** in place.
2. **With the parent's original function**, which is the historical bug.
3. **With the fix's version** of every top-level definition the fix added or
   changed in that source file, transplanted onto the parent together with any
   import it needs.

**The graded set is every test that fails in run 1 and passes in run 3.** A task
is valid only if both of these hold:

- run 2 fails at least one test that the fix added, which proves the tests catch
  the historical bug, and passes every graded test the fix did not add;
- run 3 passes every graded test, which proves a correct implementation can pass
  at the parent commit.

A candidate that fails the pre-flight may be repaired in exactly two ways. One is
a `hidden_patch_cmd` that replaces a test encoding the reference strategy rather
than the contract, with its rationale written into the patch script, as the
fingerprint task did. The other is a change to the grading command. Editing a
docstring, or dropping a graded test, to make a run pass is not allowed.
Otherwise the candidate is dropped. No session is spent on a task that hasn't
passed.

### 2.2 The grading command

`bench/run.py::score` counts only lines of the form `PASS <name>`. The runner in
`tests/test_draft.py` aborts at the first failure, so D's author and repair tasks
use a grading command that runs only the graded tests and catches each failure
separately. C (`tests/test_validate.py`) and E (`tests/test_save_skill.py`)
already catch each test's failure, and use their own runners.

## 3. The control screen

This reuses E11's rules, so the two screens are comparable.

- **6 control sessions** for each candidate that passed the pre-flight, with no
  skill installed.
- **A same-batch reference:** 3 control sessions on
  `sf-author-fingerprint-preexisting`.
- **Batch order:** C, D, E, then the reference.
- **Read the reference first.** If it resolves even once, the screen is void and
  gets re-run later.
- **Admission is 0 of 6.** A single resolved session rejects the candidate.
- **Exclusions:** a row with `session_ok: false` is excluded. If its
  `session_tail` shows the session limit, the whole screen is postponed and
  re-run as one fresh batch. Otherwise, just that session is re-run within the
  batch.
- The session allowance is probed before the batch starts.

That's up to 21 sessions. The parallel `in_scope` hardening can't affect this
screen: control sessions install no skills, so scope matching has nothing to act
on.

## 4. What follows the screen

- **Every surviving candidate is distilled (§5)**, whichever trap it ends up
  serving.
- **Assignment is computed after distillation and confirmed after the probe
  batches (§6, §7).** Trap 2 is assigned first, then trap 1 from the remaining
  survivors, and any survivor left over is a spare.
- **The traps advance independently.** If one trap ends up with no candidate, the
  other still proceeds, and only the empty trap goes back to the candidate list.
- **If nothing survives the screen,** it's back to the candidate list before any
  distillation.

## 5. Distillation

For each survivor:

- **A repair task on the same bug**, built like the repair tasks for traps A and
  B: the clone sits at the fix's parent, with the fix's test file in place. Its
  graded tests are the fix-added tests that failed in pre-flight run 2. Its prompt
  reuses the existing repair template verbatim, with the test file substituted:

  > The test suite `<test file>` has failing tests. Run `<test command>` to see
  > which ones fail, then fix the source under scripts/ so that every test passes.
  > Do not modify anything under tests/ - the tests are correct and describe the
  > intended behavior. When you are done, run the test command again to confirm.

- **The survivor is registered** in `bench/distill.py`'s `TRAPS` (letter to repair
  task) and in `bench/dryrun.py`'s `PROBES` (letter to author task).
- **Both distillers run, `learn` and `learn-failure`, with the novelty gate off**
  (`--no-novelty-gate`, as in E7), **3 draws each**. That's 6 draws per survivor,
  archived under `bench/distilled/<letter>/<distiller>-nogate/<draw>/`.
- **A draft counts only if it was saved from a repair that resolved.**
  `distill.py` already refuses to re-roll any draw whose content has been seen.

That's up to 18 sessions.

## 6. Trap assignment

### 6.1 Trap-2 qualification (deterministic, zero sessions)

Survivors are checked in the order **C, D, E**, and within each survivor, every
counted draft is checked.

For each draft, install the consolidated seven (`bench/budget_sweep.py`'s
`seven`) plus that draft through the real `save_skill.py`, into a sandboxed HOME
and project, the way `bench/real_path_check.py` does. Then run the real hook on
the survivor's author-task prompt at the shipped 1200 budget, once with `scripts/`
from `06885c0` (before the tokenizer fix) and once from `9cbb472` (after it).

**A draft qualifies** if it is **not** among the skills the old tokenizer
delivers, **and is** among the skills the new tokenizer delivers.

**Trap 2** is the first survivor, in that order, that has at least one qualifying
draft and whose probe batch reads as working (§7). If a qualifying survivor's
probe batch doesn't read as working, the next qualifying survivor in order is
considered instead. Trap 2's outcome test (§8) uses its first qualifying draft,
taking `learn` before `learn-failure` and lower draw numbers first.

### 6.2 Trap 1 and spares

**Trap 1** is chosen from the working survivors (§7) that weren't assigned to
trap 2, preferring **E, then D, then C**: the trap class furthest from A and B
comes first. Any working survivor left over is a **spare**.

## 7. Probe batches, for every survivor

Every survivor is probed, spares included.

- **A delivery check comes first, with zero sessions.** Each counted draft is run
  alone through the real hook, on its author-task prompt. A draft the hook
  wouldn't deliver is recorded as undeliverable and isn't probed, because it
  can't act as a treatment. A survivor with no deliverable draft is not a working
  trap.
- **One batch per survivor:** each deliverable draft is installed alone via
  `--skill-from` and gets 3 author-task runs, plus **3 control sessions** on the
  same task in the same batch.
- **The batch is void** if the control resolves even once.
- **A treatment row whose `injections` don't name the installed skill** is void
  and re-run. If that recurs, the draft's cell is void.
- **The survivor is working** if its deliverable drafts, pooled, resolve at least
  half of their probe runs. Each draft's own score is reported too.
- **Session limit:** handled as in §3. A batch that hits the limit is postponed
  and re-run whole.

That's up to 63 sessions.

## 8. The outcome test, for trap 2 only

Does the tokenizer fix improve outcomes with the model in the loop?

- **Library:** the consolidated seven plus trap 2's selected draft, installed via
  `--skill-from` and `--plus-skill`.
- **Two arms of 6 sessions each, in one batch, old arm first:** the plugin as
  archived at `06885c0` against the plugin as archived at `9cbb472`. Both
  snapshots are complete plugins, and outside `bench/`, `docs/` and `tests/` they
  differ only in `scripts/retrieve.py` (verified on 2026-09-13). The tokenizer is
  therefore the only difference between the arms.
- **Validity:** every old-arm row's `injections` must leave out the draft, and
  every new-arm row's must include it, exactly as qualification predicted. A row
  that doesn't match is void and re-run. If that recurs, the arm is void.
- **Criterion:** if the new arm resolves **at least 3 of 6 more** than the old
  arm, the fix improves outcomes. A difference **within 1** means no large
  effect. A difference of **2** is reported as ambiguous. Fisher's exact p is
  reported, not used as a threshold.

That's 12 sessions.

## 9. Harness changes, all under `bench/` and `tests/`

- **`bench/run.py`:** a `--plugin-dir` override, since today the plugin directory
  can only come from `tasks.json`. Every row also records the commit of the plugin
  under test, because `env` records installed plugins but not `--plugin-dir`.
- **`bench/stubs/`:** stub scripts for C, D and E, plus any justified hidden patch.
- **New scripts:** the pre-flight script (§2.1) and the qualification script (§6.1).
- **The grading command for D (§2.2).**
- **`bench/tasks.json`:** an author task for each candidate, and a repair task for
  each survivor.
- **`bench/distill.py`'s `TRAPS` and `bench/dryrun.py`'s `PROBES`.**

Nothing under `scripts/` changes. `scripts/retrieve.py`, `scripts/detect.py`,
`scripts/reconcile.py` and `bench/real_path_check.py` are left to the parallel
`in_scope` session.

## 10. Cost and pacing

Worst case, with all three surviving and every draw counting:

| stage | sessions |
| --- | --- |
| control screen | 21 |
| distillation | 18 |
| probe batches | 63 |
| outcome test | 12 |
| **total** | **about 114** |

Each batch probes the session allowance before it starts and never straddles a
limit boundary, so the work spreads across several limit windows.

## 11. Threats

1. **Candidates are thin.** Three of 19 reviewed survived, attrition at the screen
   is likely, and the rules in §4 govern what happens next.
2. **E's docstring is new.** The historical author had none, and the stub needs
   one.
3. **D's docstring nearly states the rule,** so its control may well solve it.
4. **n = 6 bounds a floor only loosely.** 0 of 6 is consistent with a true success
   rate of up to about 39%.
5. **Distilling with the gate off** produces skills the shipped distiller would
   sometimes refuse. Their provenance stays on record under `-nogate`, and trap 2
   measures retrieval, not distillation.
6. **Selection in trap-2 qualification.** Several survivors and drafts get
   checked. The rule and the order are fixed here, before any delivery is looked
   at. Qualification only decides which trap the outcome test uses; the outcome
   itself is a separate session measurement.
7. **One library.** Trap 2's library is the consolidated seven, and other
   libraries are untested.
8. **The plugin under test will change** as the `in_scope` session merges. The
   screen is unaffected, the outcome test pins archived snapshots, and every probe
   row records the plugin commit.
9. **One repository, with candidate selection reviewed by the operator.** The
   reason every candidate was dropped is recorded in §1.

## 12. Out of scope

A wider candidate search, except where §4 triggers one. The `in_scope`
hardening. Any change under `scripts/`. The shipped distiller's novelty-gate
policy.
