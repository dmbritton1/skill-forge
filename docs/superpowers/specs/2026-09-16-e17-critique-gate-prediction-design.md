# E17: does the critique gate predict whether a skill works?

**Status:** written 2026-09-16, before any E17 critique call ran. Every
criterion below is fixed before the data it governs.

## Why

Brief **Q5** — "does the `trusted` gate predict anything?" — has been open since
2026-09-09. It was attempted as a Q1 secondary and could not be read: critique
passed all 4 distilled drafts, so there was no failing group to compare
against. The register records what it needs: **drafts the gate splits on**.

E15 produced a group that splits cleanly on *outcome*, and nobody has
critiqued it:

| group | drafts | outcome on `sf-author-verdict-from` |
| --- | --- | --- |
| **V** (E15 variant, `learn-e15-nogate/1..6`) | 6 | **18/18** — 3/3 each, six independent drafts |
| **B** (E13 baseline, `learn-nogate/1..3`) | 3 | **0/9** |

One trap, one task, one batch, one model, control 0/3. All nine are
`kind: skill`, frozen on disk, and carry no critique verdict — the bench
suppresses the spawn, so every `meta.json` records only a `save` row.

If critique passes V and fails B, the gate predicts. If it gives both groups
the same verdict, it does not. Either is an answer, and it costs no bench
session.

### What the `trusted` gate actually is

`ledger.confidence()`: `critique == "pass"` **and** (`executable == "pass"`
**or** `organic_bucket == "trusted"`) **and** `fresh`. The organic half is
outcome-driven by construction, so it cannot fail to "predict". **Critique is
the conjunct that is claimed to add information, and it is required
unconditionally.** E17 measures that conjunct and nothing else.

## 1. The corpus is fixed and already exists

The nine `SKILL.md` files under `bench/distilled/C/`, verbatim. Nothing is
written, edited or regenerated for this experiment. Group membership is the
`e15_read.py` grouping, which was itself pre-registered by the E15 spec:

```
V  learn-e15-nogate/{1,2,3,4,5,6}/SKILL.md
B  learn-nogate/{1,2,3}/SKILL.md
```

## 2. The measurement

`bench/e17_q5.py` calls `validate.critique(text, {"kind": "skill"}, REPO)`
directly, exactly as `bench/critique-calibration/run.py` does.

**Three calls per draft, 27 in total.** One call per draft is not a
measurement: the calibration corpus already shows the verdict flipping on
fixed text. Case `07-commit-trailer-fixed` read `pass`, `pass`, `fail` across
three post-rubric-change runs, and case `08-gitignore-entry` — the intended
positive control — read `fail` three times out of three.

**Containment.** `critique()` is a pure function around one tool-less,
permission-less `claude -p` turn. It writes no ledger row, touches no trust
registry, installs nothing, and never reaches the operator's library.
`SKILLFORGE_VALIDATE_MODEL` stays **unset**, so the shipped default is what is
measured. Nothing under `tests/` invokes this.

**Recorded, not controlled:** critique's default model is `sonnet`
(`validate.DEFAULT_MODEL`), while every bench row in the V/B split ran
`claude-opus-5`. The gate is being measured as shipped. Each result records
the resolved CLI version and model string.

**Inconclusive is not a verdict.** `run_model` returns None on any failure and
`critique` returns `inconclusive` on a truncated or unparseable reply. An
inconclusive call is re-run **once**. A draft with 2 or more inconclusive
calls after re-runs is **dropped**, and its group's n falls with it; a group
left with fewer than 3 live drafts is not read.

## 3. Two co-primary measures

Both are pre-registered. Neither voids the other, and the second is reported
whatever the first says.

### 3.1 Does the verdict track the outcome?

Pooled over the non-inconclusive calls of live drafts: `Pv` = passes / 18, `Pb` = passes / 9 (those denominators when nothing came back inconclusive), `Δ = Pv − Pb`.
Bands reuse E15's shape rather than inventing new ones:

| Δ | with | reading |
| --- | --- | --- |
| ≥ +0.40 | Pv ≥ 0.50 | **the gate predicts** |
| \|Δ\| ≤ 0.15 | — | **the gate does not predict** |
| ≤ −0.40 | — | **the gate predicts backwards** |
| otherwise | — | ambiguous |

Fisher's exact two-sided p is reported and **never thresholded**, per this
project's convention.

Secondary, reported always: each draft's majority verdict over its 3 calls.

### 3.2 Is the verdict reproducible on fixed text?

For each draft, whether all 3 calls agree. **If fewer than 7 of 9 drafts are
unanimous, the gate is recorded as `unstable`.**

Instability does **not** void Δ. It is its own finding, and on the evidence
available it may be the more valuable half: a promotion gate whose verdict is
not reproducible on an unchanged file is a defect in the shipped path, and
nothing currently measures it above n=2. Δ is then reported with that caveat
attached.

## 4. The expected result, written down before the data

**The most likely outcome is a null**, and saying so now is what stops it
being rescued afterwards:

- critique passed all 4 drafts in the Q1 attempt;
- it failed all 9 hand-written skills in the calibration corpus, including
  both attempts at a positive control;
- so its prior is near-degenerate in both directions depending on the input,
  and a degenerate result gives Δ ≈ 0.

A degenerate result is still an answer: it moves Q5 from "unanswered, no split
available" to "does not predict outcome, n=27, on one trap". That is the whole
value on offer here, and it is small but real.

## 5. Threats

1. **Critique does not claim to do this.** Its rubric is legibility judged
   from the text alone — `followable`, `preconditions`, `checkable`. It never
   claims to predict whether the fix lands. A null therefore reads as "the
   gate measures a different thing", not "the gate is broken". Q5 asks whether
   it predicts *anything* about outcome; the answer is an answer either way,
   but it must not be written up as an indictment of the rubric.
2. **The split may be invisible to the rubric by construction.** V and B
   differ by E15's three writing rules — no test names, write the Procedure
   for first-time code, name the function up front. Those target delivery and
   application, not legibility. If the rubric is blind to exactly them, Δ ≈ 0
   is baked in and the experiment is cheap but low-information. This is the
   strongest threat to E17's value and the reason §3.2 is co-primary.
3. **n=9 drafts on one trap, one bug, one distiller (`learn`).** A null
   generalises weakly. No claim beyond this corpus is licensed.
4. **The groups differ in size** (6 vs 3) and in length (V 3192–3782 bytes, B
   2590–3116). If critique's verdict tracks length rather than content, Δ
   would be confounded. Draft length is recorded alongside each verdict so the
   write-up can say whether it moved together with the verdict; this is a
   reported diagnostic, not a correction.
5. **Different model from the bench rows.** §2 states it; it is not
   controlled, because the shipped gate is what Q5 asks about.

## 6. What this cannot answer

- Whether the **`executable`** conjunct predicts anything. It needs a
  worktree, a `verification.command` and a follow-run, and it has its own
  history of transport problems wearing verdicts (`065576b`, `ee009b5`).
- Whether critique **should** be the automatic promotion criterion. The
  calibration corpus already argues against further rubric tuning; E17 adds a
  data point and no recommendation.
- Anything about anti-skills. Every corpus member is `kind: skill`, so
  `ANTISKILL_CRITERIA` is never exercised.

## 7. Cost

27 `claude -p` turns, plus re-runs for inconclusive calls. **Zero bench
sessions, zero clones, zero writes.** Results land in
`bench/e17-q5-results.json` and are read by `bench/e17_q5.py --read`.

## Amendment 1 (2026-09-16, before any E17 call ran)

**An outage is not an inconclusive.** `critique` returns `inconclusive` both
for a reply it could not parse — which is data about the gate — and for a
model call that never happened, which is not. At the session limit every call
would come back inconclusive, §2's "two inconclusive drops the draft" rule
would drop all nine, and the batch would record a verdict about the drafts
that is really a verdict about the clock.

From now on, a call that is inconclusive twice asks `claude -p` a trivial
question first. If that answers, the inconclusive is genuine and is recorded
as §2 says. If it does not, **nothing is recorded for that call** and the run
stops; finished calls are kept in `bench/e17-q5-results.json` and a later run
resumes from them.

This changes no reading rule, no band, no count and no group. It was written
before the first call, so no E17 data existed to contaminate it.
