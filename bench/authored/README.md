# Archived authored artifacts

What each bench session actually wrote, extracted 2026-09-10 from the clones
under `/tmp/skillforge-bench` before anything swept them.

`bench/run.py` never cleaned its work directory, so the clones from every
batch this project has run were still on disk. `prepare()` deletes and
recreates a clone per path segment, so **only the most recent run for each
segment survived** — this is one artifact per cell, not one per historical
row in `results.jsonl`.

## What is here

| | |
|---|---|
| diffs | 54 |
| author-task cells (3 runs each) | 14 |
| distillation clones | 12 |
| median diff | 134 lines |

Each `<clone>.diff` is `git diff HEAD` inside that clone: the authored source
change plus the harness-staged hidden tests. `manifest.json` maps every diff
to its task, arm, path segment, run index and base commit.

The segment tells the batch apart: `-plus` is E6's arm R+I, `-hot` is E5/the
hot-path confirmation, `-d-*` is a Q1 distilled draft, empty is the plain
treatment or control arm.

## Why this exists

A graded scorer over the authored function is the project's next piece of
measurement infrastructure. It needs artifacts to grade, and these are the
only ones that exist — no experiment here has ever stored its output beyond
a pass/fail bit. This corpus lets a rubric be applied retrospectively to
E1, E5, Q1 and E6 without spending a session.

**Pre-register the rubric before reading these diffs.** Deriving grading
criteria from artifacts you have already looked at, then scoring those same
artifacts, produces a result about the rubric rather than about the data.
Take the criteria from each task's own docstring contract, commit them, then
score.

## The full clones, including the per-run ledgers

`~/skillforge-bench-archive/skillforge-bench-clones-20260910.tar.gz`, 25 MB.

That tarball matters beyond the diffs: it holds 54 per-run `ledger.db` files,
and for every batch before 2026-09-09 those ledgers are the **only** copy of
the delivery evidence. Rows from 09-09 onward carry `injections` on the row
itself; earlier rows do not. It is outside the repo and outside `/tmp`, so it
survives a reboot and a `git clean -fdx`, but it does not travel with this
branch. Copy it deliberately if you move machines.
