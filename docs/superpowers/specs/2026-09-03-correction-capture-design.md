# Correction capture — design

**Status:** proposed
**Replaces** the exit-code struggle trigger (slice D1: `signals`,
`log_signal`, `struggle_targets`). Amends parent spec §9.1's capture model and
§9.3's context budget.

## Problem

The automatic capture path has never produced a draft. The `drafts` table is
empty, and that is not low usage — three independent defects each make it
impossible.

**One: the outcome field does not exist.** `detect.bash_outcome` reads
`is_error`/`isError` from the tool response. Across 2441 real tool results in
this project's transcripts, neither key appears once. So `outcome` is always
`None`, and `_log_signal` is gated on `outcome is not None`. No breadcrumb has
ever been written.

**Two: the hook never hears about failures.** `PostToolUse` fires only after a
tool call *succeeds*; failures fire `PostToolUseFailure`, which SkillForge does
not register. Even with a correct `bash_outcome`, `detect.py` could only ever
record successes — and `struggle_targets` needs two failures.

**Three: the pattern does not occur.** Replaying 1561 real Bash calls through
the shipped `target_key` and `struggle_targets`: **zero** struggles. Of 1286
distinct (session, command-key) pairs, 22 ever failed, 2 reached two
consecutive failures, and 6 failed then recovered — with **no overlap** between
the last two sets. The keys that failed enough never recovered on the same key;
the keys that recovered never failed twice running. Recovery changes the
command, so the success lands on a different key than the failures.

### The deeper problem

Even with all three fixed, the trigger assumes struggle looks like a non-zero
exit. Much of it does not. The most expensive failures are the ones that exit
0 and return the wrong thing: a request with the wrong field names, a query
that silently reads a column name as a string literal, a test that passes
without testing anything. Exit codes are blind to all of it.

The motivating case is an API integration debugged over an hour. Its signal was
not crashes. It was the user repeatedly saying *that's not right*.

## The signal

**A user correction.** When the user redirects the model, that is the moment the
model's default was insufficient — which is precisely the question the
distillation contract's novelty gate currently asks the model to guess about
itself. It needs no error parsing, has no signature-identity problem, and sees
exit-0 failures.

## Delivery

`sync.py` (SessionStart) prints a `CORRECTION_NOTE` on stdout. `SessionStart`
is one of four events whose plain stdout becomes visible context, and `sync.py`
already writes there (the quarantine notice), so the route exists.

SessionStart also fires with `source: "compact"` after every context
compaction. The instruction therefore **re-delivers itself** exactly when a
compaction summarised the previous copy away — no turn-count cadence, no
per-session dedupe state.

This is why delivery is not `retrieve.py`'s injection payload, which carries
`MARKER_NOTE`. That payload ships only past two early returns — `if not idx`
and `if not picked` — so it is silent both when nothing matched and, more
importantly, when no index exists at all. A fresh install with no skills would
never receive it, and a fresh install is exactly where capture matters most.

**Budget.** ~100 tokens per SessionStart, ~35 per correction written. A normal
session with three corrections costs ~205 tokens; a heavy session with two
compactions ~405. Against §9.3's stated "zero context tokens" this is a
deliberate amendment, not drift: the compared alternative (an always-loaded
observer skill) costs ~7,850 tokens unconditionally, and SkillForge can buy the
same signal at ~3% of that because its bookkeeping lives in SQLite rather than
in the conversation.

## The mark

The model appends one line to the existing
`<cwd>/.claude/skillforge/session-usage.jsonl`:

```json
{"event": "correction", "what": "<one line: what you had wrong>"}
```

Same file as the usage marker, same consume-on-read, same untrusted-input
discipline. `reconcile.read_markers` generalises to `read_scratch(cwd)`
returning `(skills, corrections)` — one reader, because the file is deleted as
it is read and two readers cannot both consume it.

Because the file is deleted as it is read, a correction cannot simply wait in
it until it settles. The reconciler therefore moves each correction into the
`corrections` table on first read, stamped with the read time, and nominates
from that table later. The scratch file is a mailbox, not storage.

The instruction carries an explicit **do-not-log list**, which is the most
transferable idea from prior art in this space: one-off typos, the user
changing their mind about what they want, a preference already recorded, and
anything the model would have got right with more care rather than more
knowledge. A stated negative space is more actionable than the novelty gate's
introspective question.

## Corroboration

A self-report alone is what comparable systems have, and it is the weakest part
of them: the model both decides it was corrected and records it, with nothing
checking. A model that has just been corrected is a poor narrator of that
correction, and nothing distinguishes a correction from a feature request.

So `detect.py` independently records every file the model edits — a row per
`Edit`/`Write`/`NotebookEdit` — and the reconciler cross-checks. A real
correction is followed by **rework**: files touched again.

| marked | rework | reading |
|---|---|---|
| yes | yes | corroborated — the signal working as intended |
| no | yes | silent redirect — user steered without saying so |
| yes | no | possibly a feature request misread as a correction |
| no | no | ordinary turn |

**Corroboration is recorded, not enforced.** Every marked correction nominates
(subject to the settle clock and the cost floor); whether rework corroborated it
is stored alongside and reported, never used to reject.

That is a deliberate choice against precision. A too-strict gate producing zero
nominations is the exact failure this whole design exists to escape, and
corroboration is coarse enough to cause it: "the same file was edited again"
misses any correction resolved by a command rather than an edit, by a config
change outside the repo, or by the model simply doing the next thing right.
Meanwhile two filters already stand downstream — the drafter's `ABORT` contract
and the novelty gate, then human approval before any skill is saved. A weak
nomination costs one model call that aborts; a rejected real correction costs
the lesson entirely.

Row two is a category a pure self-report cannot detect at all. This slice
records it; acting on it is deferred (see Non-goals).

As with the marker layer, this makes the design measure its own validity: if
marks rarely corroborate, that is the data saying to drop the self-report and go
structural. Recording the rate rather than gating on it is what keeps that
measurement available — a gate would suppress the very cases that reveal it.

## Cost weighting

Turns and edit rows between the correction and its nomination, derived from the
same table. This ranks an hour-long integration fight above a one-word fix.
Cost is the closest available proxy for *would I want this one-shot next time*,
and it gives an ordering rather than an undifferentiated pile.

Nomination requires a minimum cost — `MIN_CORRECTION_EDITS = 2` edit rows
after the correction — so a correction followed by one trivial edit does not
spend a model call. Two is the floor rather than a tuned value: one edit is a
typo fix, and the distillation contract would abort on it anyway.

## Nomination timing

The old trigger fired *after* the fix succeeded. A correction fires *before*
it: at the moment it is written, the resolution has not happened yet. So
nomination must wait.

A correction becomes eligible when it has settled — no newer correction in the
session and `CORRECTION_SETTLE_S = 300` seconds elapsed — or at `SessionEnd`,
whichever comes first. Five minutes is deliberately shorter than the existing
`RECONCILE_WINDOW_S = 900`: that window bounds how long a skill's fate stays
open, whereas this one only needs to outlast the model's response to the
correction, and a shorter clock means more corrections settle before the
session ends rather than all arriving at once.

The evidence window handed to the drafter runs from the correction's timestamp
to nomination, so it contains the correction and whatever followed it.

The nomination gate is therefore two conditions, not three: **settled** and
**at least `MIN_CORRECTION_EDITS` edit rows after it**. Corroboration is not
consulted.

A nomination spawns a drafter immediately and detached, at most one per session
at a time — `reconcile.draft_blockers` already enforces that cap and is reused
unchanged. Each spawn is a real `claude -p` call, so the cost floor is doing
double duty: it keeps trivial corrections from drafting, and it is the only
thing bounding spend in a session full of small redirections.

## Drafter changes

`draft.PROMPT_HEAD` currently asserts:

> The session got stuck: the command `__TARGET__` failed repeatedly and then
> succeeded.

Under this trigger that sentence can be false, and telling a model a success
happened is an efficient way to make it invent one. It is replaced with a
correction-shaped head: here is what the model got wrong, here is what followed,
distil the lesson — and **`ABORT` if the correction was never actually
resolved.**

Letting the drafter judge resolution is deliberate. A token matcher cannot
distinguish "fixed" from "gave up" or "changed approach"; a model reading the
window can. The old trigger died on exactly that conjunct, and the drafter
already has an `ABORT:` contract and a novelty gate to refuse on.

## What is removed

The exit-code struggle trigger, in full: `ledger.log_signal`,
`ledger.prune_signals`, the `signals` table and its index, `SIGNAL_SQL`,
`reconcile.struggle_targets`, and `detect._log_signal` with its call site.

`prune_signals` has two call sites — `sync.py` (TTL sweep) and `reconcile.py`
(at SessionEnd). Both are repointed to a `prune_scratch` that clears `edits`
and `corrections` on the same schedule, so the sweep survives the removal
rather than being dropped with it.

Leaving it in place would mean carrying a trigger that provably never fires
alongside its replacement. The measurements above are the justification, and
they are reproducible from the transcripts.

## Data

Two new tables, added to `SCHEMA`. `connect()` runs `executescript(SCHEMA)`
unconditionally, so `CREATE TABLE IF NOT EXISTS` reaches existing databases with
no version bump and no migration — the same property the marker index relied on.

```sql
CREATE TABLE IF NOT EXISTS edits (
  id INTEGER PRIMARY KEY,
  session TEXT NOT NULL,
  prompt_id TEXT,
  path TEXT NOT NULL,
  ts TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_edits_session ON edits(session, id);

CREATE TABLE IF NOT EXISTS corrections (
  id INTEGER PRIMARY KEY,
  session TEXT NOT NULL,
  what TEXT NOT NULL,
  status TEXT NOT NULL,      -- pending | nominated | discarded
  corroborated INTEGER,      -- NULL until evaluated, then 0 or 1
  ts TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_corrections_session ON corrections(session, id);
```

`read_scratch(cwd)` returns `(skills, corrections)` where `corrections` is a
list of `what` strings in file order; the reconciler stamps each with the read
time as it inserts. `status` moves `pending → nominated` when a drafter is
spawned, and `pending → discarded` at `SessionEnd` for anything that never met
the cost floor — so a re-run nominates nothing twice and the table does not
accumulate.

Both are scratch, not history — pruned at `SessionEnd` and swept by TTL at
sync, exactly as `signals` was. It is not an `events` row: `events.skill` is `NOT NULL` and an
edit belongs to no skill.

`prompt_id` is recorded because both `PostToolUse` and `PostToolUseFailure`
carry it, and it makes turn boundaries exact rather than inferred from
timestamps. See Open questions for the one place this matters.

## Security

The correction's `what` text is **model-written free text that reaches a model
prompt** — a wider surface than the old `--target`, which was a tokenized
command string.

- capped at `MAX_CORRECTION_CHARS = 500` before storage and before use — one
  line of description, generous enough not to truncate a real one
- passed as a list-form `Popen` argument, never through a shell
- substituted into the prompt under `PROMPT_HEAD`'s existing untrusted-data
  instruction, which already tells the drafter the evidence may contain text
  that looks like instructions and must be distilled, never obeyed
- the scratch file is parsed by a script and never handed to a model verbatim

## Testing

No suite may invoke a model, run a skill-authored command, or create a git
worktree. Nothing here needs any of those.

**Parsing** — a correction line; a mixed file of skill markers and corrections;
malformed JSON; an `event` value that is not `correction`; a `what` that is not
a string; oversize `what` truncated; the file consumed even when only
corrections were present.

**Corroboration** — a correction with a re-edited file records corroborated; one
whose only edits touch different files records uncorroborated; edits from a
different session never corroborate this one. Critically: **an uncorroborated
correction still nominates**, which is the test that pins corroboration as
metadata rather than a gate.

**Nomination** — a settled correction nominates once; an unsettled one does not;
a newer correction resets the settle clock; `SessionEnd` nominates regardless of
the clock; a correction below `MIN_CORRECTION_EDITS` never nominates; one
nomination per correction per session; a second nomination while a drafter is
already running is deferred, not dropped.

**Mutation** — removing the settle check must fail the unsettled test; removing
the cost floor must fail the trivial-correction test; making corroboration a
gate must fail the uncorroborated-still-nominates test.

## Parent spec amendment

`docs/skillforge-architecture-v4.md` is updated in this slice rather than left
to drift. Two places go stale the moment this ships:

- **§9.1's capture model** describes struggle detection via repeated command
  failure. That path is removed here; the section is rewritten to describe the
  correction signal, with the measured reason the old one is going rather than a
  bare replacement.
- **§9.3's cost budget** claims zero context tokens for the detection pipeline.
  It gains the ~100-tokens-per-SessionStart and ~35-per-correction figures, and
  the note that SessionStart re-fires on compaction so the charge recurs.

The v0.2 roadmap line in §13 keeps its wording: "the usage-detection core"
still ships, by a different trigger.

This is scoped deliberately. Last slice's whole-branch review named the pattern
— the plan gets corrected while the spec silently drifts — as a recurring
defect, and it recurred five times in that slice alone.

## Non-goals

**Fixing `bash_outcome` / registering `PostToolUseFailure`.** Still required —
without it no `verification` detection carries an outcome, so `success_sessions`
stays 0, nothing reaches `working`, the hot tier stays empty and the Tier A
conjunct's organic half is unsatisfiable. But it feeds *trust*, not *capture*,
and this slice is capture. Now a small change: register the event and read its
`error` field, rather than the error-string parsing an earlier draft of this
work proposed.

**Acting on silent redirects (row two).** Recorded, not acted on. It needs its
own calibration — distinguishing a silent redirect from ordinary iteration is
the same ambiguity that sank the exit-code trigger. This slice needs the
corroboration rate on marked corrections first — without knowing how often a
mark and observed rework agree, there is no basis for trusting rework on its
own.

**Retrieval-miss detection** — a skill injected and the user corrected anyway,
which is evidence the skill or its triggers were wrong. Valuable and unique to
SkillForge, but it produces data only once skills are routinely injected, which
needs the trust half working.

**Error-output capture.** Deferred on evidence: a strict anchored-marker scan
over the same transcripts flagged 3.2% of tool results, of which the second most
common signature was `FAILED: none` — the literal success message of the test
runner. Detection is answerable structurally via `PostToolUseFailure` if this is
ever revisited.

## Ceilings and open questions

**Compliance is not enforceable.** Models forget protocols. That is assumed, not
designed against — it is why corroboration exists and why the disagreement rate
is recorded rather than the mark being trusted alone.

**Corroboration is coarse.** "The same file was edited again" is a proxy for
rework. It will credit a correction whose follow-up edit was unrelated, and miss
one resolved by a command rather than an edit.

**Same-turn fixes may under-corroborate.** The reconciler stamps a correction at
the Stop of the turn it was written in, so a fix landing inside that same turn
has edit rows timestamped fractionally earlier. `prompt_id` resolves this
exactly — edits and correction share a turn id rather than being ordered by
clock. **Open question for implementation: whether the `Stop` payload carries
`prompt_id`.** If it does, corroboration keys on it. If it does not, it falls
back to timestamps and under-corroborates fast fixes.

Because corroboration does not gate nomination, the cost of getting this wrong
is a skewed metric rather than a lost capture — the correction still drafts. But
the metric is the thing this design offers over a pure self-report, so a
systematic undercount on the fastest fixes would quietly understate how well the
marks work.

**Concurrent sessions in one repo share one scratch file.** Two sessions in the
same tree can cross-read corrections. The old marker layer bounds this with an
injection gate; corrections have no equivalent gate, so a correction written by
one session can be nominated by the other. Both would draft from their own
transcript, so the damage is a wasted model call rather than wrong evidence.
