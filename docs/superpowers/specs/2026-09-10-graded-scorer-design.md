# Graded scoring for the bench — partial credit over the authored function

Design written 2026-09-10, after E6. Nothing here has been run. The figures in
§2 were measured; every other number is a slot.

## The question

**Can this bench resolve anything smaller than all-or-nothing?**

`resolved` is `all(per_test.values())`. Three experiments in a row have hit the
ceiling that creates:

- **E4** cannot run at all. It needs a task whose control baseline is neither 0
  nor 100%, and a binary score gives a 0/6 control nowhere to fall *by
  construction*.
- **E6** returned 6/6 against 6/6. That cannot distinguish no effect from a
  small one.
- **E5** measured one arm twice and got 6/6 and 4/6, a spread wider than the
  effect it was trying to resolve.

All three are the same defect. It is the scorer, not the tasks.

## 1. The partial credit that already exists does not work

Before building anything, the cheaper option was checked: each task already
declares two `fail_to_pass` tests and every row already records `per_test`, so
a 0/1/2 scale is sitting in the data. Across all 96 rows in `results.jsonl`:

| `per_test` outcome | rows |
|---|---|
| 0 of 2 | 38 |
| 1 of 2 | 1 |
| 2 of 2 | 57 |

One row in ninety-six lands in the middle. The two hidden tests per task are
near-perfectly correlated — a session either sees the trap or it does not — so
the existing gradation is degenerate. This is the evidence that a real probe
suite is needed rather than assumed.

## 2. Viability — measured, not assumed

**The archived artifacts replay.** `bench/authored/` holds 54 diffs, 42 of them
author-task runs, extracted from the bench clones on 2026-09-10. Applying only
the `scripts/` portion of each onto its base commit:

| | |
|---|---|
| author-task diffs | 42 |
| applied cleanly | 42 |
| failed | 0 |
| distinct base commits | 2, both reachable |

So a finer-grained suite can be run against every surviving historical run at
**zero session cost**. The source-only filter matters: the full diff also
carries the harness-staged hidden tests, and replaying those would reinstate
the old two-test grading instead of the new suite.

**The two contracts are unevenly specified**, and this shapes where probes come
from. The stubs are the contract the session actually reads.

`stub_response_text.py` states three things — a string may arrive, a structured
object may arrive, truncate to `MAX_OUTPUT_CHARS` — and its own comment says
naming the hazard "would hand over the very knowledge the benchmark is trying
to measure". `stub_fingerprint_preexisting.py` states seven: use `git grep`
then `patterns.matches()` to confirm, return 1 on present, 0 on absent, None
for each of three named unknown conditions, and honor `GIT_TIMEOUT_S`,
`SNAPSHOT_MAX_FILES` and `SNAPSHOT_MAX_BYTES`.

One task's probes therefore derive from the contract directly. The other's must
come from enumerating the input space.

## 3. Design

Two halves, scored separately, reported together.

### 3.1 Probe suite — zero sessions

New files under `bench/probes/`, one per task. Each probe is an independent
assertion, run in isolation, so one failure cannot abort the rest. `bench/`
rather than `tests/` because the repo suite must stay a suite; and per
`bench/critique-calibration/README.md`, `tests/` is forbidden from invoking a
model, which the judge half does.

**`probe_response_text.py`** — three from the contract, six from systematic
input enumeration:

1. a plain string under the cap returns unchanged
2. a plain string over the cap is truncated to `MAX_OUTPUT_CHARS`
3. a flat dict yields text containing its values
4. a nested dict yields text containing values at depth
5. non-string leaves (int, None, bool) survive into the text
6. a non-JSON-serializable object does not raise
7. a large structure never exceeds `MAX_OUTPUT_CHARS`
8. `patterns.tokenize()` over the result recovers a flat dict's value tokens
9. the same, nested

**`probe_fingerprint_preexisting.py`** — nine from the contract, two the trap:

1. returns 1 when a fingerprint is present
2. returns 0 when none is present
3. returns None outside a git repository
4. returns None when git is missing
5. returns None when the subprocess timeout fires
6. passes `GIT_TIMEOUT_S` as the subprocess timeout
7. examines at most `SNAPSHOT_MAX_FILES` candidates
8. reads at most `SNAPSHOT_MAX_BYTES` from any one file
9. confirms via `patterns.matches()` rather than trusting the raw grep hit
10. a non-match after the **file** cap truncated the search returns None, not 0
11. a non-match after the **byte** cap truncated the search returns None, not 0

Probes 10 and 11 are **not** contract-derived, and the distinction matters. The
stub names three unknown conditions — not a git repo, git missing, timeout —
and a fired cap is deliberately not among them. That omission is the trap, and
it is why these two probes sit at the top of the difficulty range while probes
1 through 9 span the middle.

Probes 8 and 9 of the first suite and probes 10 and 11 of the second are the
existing `fail_to_pass` tests. The new suite **subsumes** the old one rather
than replacing it, so every graded score stays anchored to the binary result.

`probe_score` is the fraction passing.

### 3.2 Judge — one session per artifact

Follows `bench/judge.py`: retrospective, file-based, unsteered, one `claude -p`
turn per artifact, with the batch already finished. It scores what an assertion
cannot:

1. Is the unknown-versus-absent distinction explicit — a named branch or a
   comment — or does it fall out incidentally?
2. Are the bounds documented where they are used, or are they bare constants?
3. Does the code degrade visibly on unexpected input rather than silently?

`judge_score` is the fraction of criteria met.

### 3.3 Combination, and what is recorded

Three numbers per run: `probe_score`, `judge_score`, and `graded`, the
unweighted mean of the two.

**The mean is a guess.** No evidence sets the weighting, and this document is
saying so rather than implying a derivation. The two halves are recorded
separately precisely so a reader can ignore the combination and use either.

`resolved` is **supplemented, not replaced**, so every published result stays
comparable. Rows land in a new `bench/graded.jsonl`; `results.jsonl` is
append-only and tied to the binary design, and mixing schemas into it is how
the register's row count went stale.

### 3.4 Replay driver

`bench/regrade.py`: for each `bench/authored/manifest.json` entry, check out the
base commit in a scratch worktree, apply the diff filtered to `scripts/*`, run
the probe suite, run the judge, append a row keyed by clone name so it joins
back to `results.jsonl`.

### 3.5 Calibration

The judge half gets a fixed corpus with hand-established graded verdicts,
mirroring `bench/critique-calibration/`. Its README makes the argument: tuning
a rubric against freshly written examples means grading your own homework, and
you learn only that you can move a threshold. Fixed inputs with known answers
turn that into a measurement.

## 4. Pre-registration

Fixed before any archived diff is read.

- The probe assertions in §3.1, the judge criteria in §3.2, and this
  falsification condition are committed **before** `regrade.py` runs.
- **Falsifier: if `probe_score` comes back bimodal** — every artifact at 0.0 or
  1.0, with the middle as empty as the 1-in-96 the binary scale produced — the
  graded design has failed. It is reported as failed. It is **not** tuned by
  adding or dropping probes until the distribution separates.
- The probe suite subsumes the existing `fail_to_pass` tests, so any artifact
  whose `resolved` was true must score at least those probes. A violation is a
  harness bug, not a finding.
- Probe and judge scores are reported separately in every result. The combined
  `graded` is never reported alone.
- No probe is added, removed or reworded after scores are seen.

## 5. Threats

1. **The author of this spec has partially seen one artifact.** While testing
   diff extraction on 2026-09-10, roughly twenty lines of
   `sf-author-response-text-treatment-1.diff` were printed, along with the
   authored body line counts of two runs. The probe list above was written from
   the stubs, not from that fragment, and the `response_text` suite is the one
   affected. It is disclosed rather than assumed harmless.
2. **Designing probes that span difficulty is adjacent to knowing the answer.**
   The mitigation is that §3.1's non-contract probes come from enumerating the
   input space — scalar, flat, nested, non-serializable, at cap, past cap —
   rather than from reading any solution. It is a weaker guarantee than the
   `fingerprint` suite's, which is contract-only.
3. **The judge adds a second source of variance** to a design whose spread
   already exceeds its effects, and `bench/RESULTS.md` records a judge that
   found the opposite of the scores on Q1. Separate reporting makes a
   disagreement visible; it does not reduce the variance.
4. **42 judge sessions**, before calibration cases, against a session meter that
   is the binding limit — the Q1 session spent about 75 and could not start
   another. Check the meter before the batch.
5. **One artifact per cell, not one per row.** `prepare()` deletes and recreates
   a clone per path segment, so batches re-run under the same segment
   overwrote their predecessors long ago. The corpus cannot reconstruct every
   historical row.
6. **A graded score does not unblock E4 by itself.** It removes the *scoring*
   floor. Whether control then lands in the mid-range is an empirical question
   this design does not answer.

## 6. How to read the outcome

- **Probe scores spread, control in the mid-range.** E4 becomes runnable and
  every future experiment gains resolution. The primary success case.
- **Probe scores spread, control still at the floor.** The scorer works and E4
  stays blocked on the task, which would confirm the diagnosis in §3.2 of the
  handoff was wrong about where the blockage sits.
- **Probe scores bimodal.** §4's falsifier fires. Report and stop.
- **Probe and judge disagree sharply.** Report both, claim neither, and treat
  the calibration corpus as the next piece of work.

## 7. Out of scope

Re-running any session. Changing `resolved` or any published result. The
repair-mode tasks, whose control sits at the ceiling for a different reason.
Turns-to-completion, which the pilot rejected as high-variance and gameable —
that rejection stands and this design does not revisit it.
