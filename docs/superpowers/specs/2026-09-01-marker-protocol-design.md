# Marker protocol and the usage truth table — design

**Status:** proposed
**Implements:** parent spec §9.1, the marker layer and the Stop-time truth
table. Supersedes nothing; adds a signal alongside the verification, symptom
and fingerprint layers already in place.

## Problem

Three of the four usage detectors in §9.1 exist. The PostToolUse hook matches
Bash calls against `verifications.json` and anti-skill signatures against
`symptoms.json`; `retrieve.probe_fingerprints` takes the injection-time
snapshot; the Stop reconciler greps the session diff for fingerprints. All
four are *passive* — they infer use from residue.

Nothing asks the model what it actually did. That gap costs two distinct
measurements:

**Convention skills are invisible.** A skill whose correct application leaves
no distinctive fragment in the diff — a naming rule, an ordering constraint,
something you follow by *not* writing the wrong thing — can be followed
perfectly and register nothing. It then reads as injected-but-never-used, and
§9.1 is explicit about where that leads: an undercounted
`injection_to_use_ratio` "narrows a good skill's triggers as punishment for a
matching bug." Undercounting is the corrosive direction.

**Nothing cross-checks the passive layers.** A fingerprint appearing in a diff
is evidence the procedure was applied, but it is only evidence. Without a
second, independent signal there is no way to ask how often the two agree —
and "how often does the marker disagree with the fingerprint" is exactly the
meta-loop input §9.2 says an aggregate-only schema cannot answer.

## The signal

The model appends one line per applied skill to a session scratch file. At
Stop, the reconciler ingests those lines and writes one `detection='marker'`
event per skill per session, under the same crediting rule the verification
layer already uses.

The truth table from §9.1 is then **not stored**. Per `(session, skill)` the
ledger holds some subset of `{marker, fingerprint, verification}` detection
rows, and which cell the session falls in is a query over those rows:

| marker | fingerprint or verification | reading |
|---|---|---|
| yes | yes | clean usage, signals agree |
| no | yes | used; the usage protocol drifted (**compliance miss**) |
| yes | no | claimed but uncorroborated (**performative**, or an unfingerprintable skill) |
| no | no | not used |

Deriving rather than storing dissolves the ordering problem for free. A marker
at turn 3 and a fingerprint at turn 7 need no upgrade step, because nothing was
adjudicated in between. It also matches §9.2's own rule: aggregates are views
over events, never a substitute for them.

## Why marker-only still counts as a use

§9.1 says to "discount as likely performative" a marker with no corroboration.
This design records it as a use anyway, distinguishably. The reason is that the
risk is asymmetric and the asymmetry is measurable.

A `detection='marker'` row carries a null outcome. `skill_confidence` derives
buckets purely from `outcome='success'`/`'failure'` counts, so a performative
marker **cannot manufacture a success, cannot reach the Tier A conjunct, and
cannot promote anything**. Its entire blast radius is `uses` (feeding
`injection_to_use_ratio`) and `last_used` (feeding the 90-day freshness
clause), and it is capped at one row per skill per session.

Against that: discarding marker-only evidence silently zeroes the usage count
of every skill whose application is real but diff-invisible — the convention
skills above, which are also the class the critique rubric already treats
harshly. Overcounting costs a slightly stale trigger set. Undercounting
punishes working skills for a property of their own subject matter.

The performative rate is recorded rather than assumed, so if it turns out large
this decision can be revisited against data instead of introspection.

## Delivery

One shared constant in `retrieve.py`, appended once per injection payload —
not once per skill — in both `retrieve.run_hook` and `detect.run`:

```python
MARKER_NOTE = ('--- SkillForge: if you apply any skill above, append one line to'
               ' .claude/skillforge/session-usage.jsonl (create it if absent):'
               ' {"skill": "<skill-name>"} ---')
```

Roughly 35 tokens, charged only in sessions that inject something, and zero in
sessions that inject nothing. `detect.py` already imports `retrieve`, so the
wording exists once.

That covers warm skills, which SkillForge injects itself. Hot skills it does
not: the harness injects those from the native directory and SkillForge never
observes it. They get the same note by a second route.

**Hot skills — appended to the materialized body.** `sync.materialize_one_text`
is the single point where a hot skill's text lands in
`.claude/skills/skillforge-hot/<name>/SKILL.md`; `save_skill.native_dir` uses
that path only for collision checks and never materializes. Appending
`MARKER_NOTE` to the text `sync` writes there puts the instruction in the
skill's own body, naming that skill.

This is deliberately not §9.1's `skillforge-usage` engine skill, and the reason
is the same fact that would have broken the engine skill. A native skill under
`.claude/skills/` is progressively disclosed: its description sits in standing
context, its *body* loads only when the model reaches for it. `sync` says as
much in its own budgeting — hot tier is charged
`est_tokens(s["description"])`, not the body. A protocol living in a *separate*
engine skill's body is therefore in context only once the model has already
decided to go read that protocol, which is the behaviour the protocol exists to
prompt. Appending to each hot skill's own body inverts that: the body loads
exactly when the model intends to apply the skill, which is the moment the
instruction is needed.

The two routes cost differently and both are cheap. The preamble is charged
per injecting session and zero otherwise; the appended note is charged only
when a hot skill's body is actually opened, and nothing in standing context,
because hot budget is charged on the description.

Neither route disturbs the trust registry. `hashes` and `trust.check_text` both
run on `s["text"]`, the source store file; the materialized copy is never
re-hashed or re-checked, and nothing else reads it.
`materialize_one_text`'s idempotence survives because it compares the target
against the text it is handed, which now includes the note.

**Fields dropped from §9.1's `{skill, action, ts}`.** The ledger timestamps its
own row, so `ts` is redundant. `events` has no free-text column to hold
`action`, and the file is consumed on read (below), so nothing durable would
keep it — asking the model to write a field with no consumer is cost without
benefit. Both are cheap to restore if a human-readable audit trail is wanted
later.

## The marker file

`<cwd>/.claude/skillforge/session-usage.jsonl`, inside the already-gitignored
`.claude/skillforge/`.

It is **read and then unlinked**. Consuming rather than accumulating is
required, not tidiness: the model has no session id to write, so the file is
not session-scoped, and a line surviving from an earlier session would credit
the current one the next time that skill is injected.

The file is untrusted input — model-written, and the model's context may
contain hostile tool output. The read is capped at 64 KiB (matching
`detect.MAX_OUTPUT_CHARS`), parsed line by line with malformed lines skipped,
each name truncated to 128 characters, and every name checked against the index
and the crediting gate before it becomes a row. It never reaches a model: a
script reads it and turns it into ledger rows.

## Ingestion

A new `read_markers(cwd)` in `reconcile.py`, returning the set of skill names
the model claimed to apply and consuming the file as it reads.

Called at the top of `_reconcile_c2`, above its `if not state: return` guard. A
hot skill can produce a marker with no other ledger events at all, so ingestion
cannot sit behind a guard keyed on events existing. The guard becomes
`if not state and not markers: return`.

This keeps the reconciler's cheap path cheap. `load_entries()` still runs only
when there is work, and the common no-marker case costs one failed `open` on
top of the indexed SELECT the hook already does every turn.

## Crediting rules

A marker becomes a `detection='marker'` row only when all of the following
hold:

1. the name resolves to an entry in `index.json`;
2. that entry is `in_scope` for this cwd;
3. no marker row exists for this `(session, skill)` yet — read off
   `session_state`'s `detections` set, which is already computed;
4. the skill was injected this session (`injected_ts is not None`) **or** its
   tier is `hot`.

Rule 4 is `credited()` from the outcome-attribution work, verbatim. The
confound is identical — a claim of use is a proxy, and an ungated proxy credits
a skill whose text never reached the model — and so is the hot exemption's
justification: the harness injects hot skills from the native directory and
SkillForge never observes it, so requiring an injection event would make
markers useless for the one tier that has no other way to be seen. Restating
the rule rather than inventing a second one keeps a single answer in the
codebase to "may this skill claim credit."

A partial unique index backstops rule 3, alongside the existing ones in
`ledger.py`. Those are applied in a loop outside `SCHEMA`, so a new one reaches
existing databases without a version bump or a migration.

## Read surface

`ledger.usage_for(skill)` returns injection and per-detection-type counts.
`library show` prints them with the two derived rates: fingerprint-without-
marker is the compliance-miss rate, marker-without-corroboration is the
performative rate.

`/stats` is not built here. It is its own v0.2 line item and wants a
library-wide view rather than a per-skill one.

## Files touched

- `scripts/retrieve.py` — `MARKER_NOTE`; append it to the injected payload in
  `run_hook`.
- `scripts/detect.py` — append `retrieve.MARKER_NOTE` to the anti-skill payload.
- `scripts/sync.py` — append `retrieve.MARKER_NOTE` to the text passed to
  `materialize_one_text`.
- `scripts/reconcile.py` — `marker_path`, `read_markers`; marker ingestion and
  crediting at the top of `_reconcile_c2`; relax its early return.
- `scripts/ledger.py` — `usage_for`; the partial unique index on
  `(session, skill)` for `detection = 'marker'`.
- `scripts/library.py` — print usage counts and the two rates in `cmd_show`.
- `tests/test_reconcile.py`, `tests/test_ledger.py`, `tests/test_retrieve.py`,
  `tests/test_detect.py`, `tests/test_sync.py` — per the Testing section.

No schema version bump: `events` already has every column this needs, and the
new index is added to the loop that runs against existing databases.

## Testing

No suite may invoke a model, run a skill-authored command, or create a git
worktree. Nothing here needs any of those: it is a tmpdir and a ledger.

**Parsing** — valid lines; blank lines; malformed JSON; a line that is valid
JSON but not an object; an object whose `skill` is not a string; a file past
the size cap; a missing file; and that the file is gone after a read.

**Crediting** — a marker for a warm skill injected this session yields one row;
a marker for a skill never injected yields none; a marker for a hot skill with
no injection event yields one row; a marker for an out-of-scope entry yields
none; a marker for a name absent from the index yields none; a second Stop in
the same session yields no duplicate.

**Truth table** — a session with a fingerprint and no marker and a session with
both produce different `usage_for` counts.

**Delivery** — the injected payload carries `MARKER_NOTE` exactly once when
several skills are injected together; a materialized hot skill's `SKILL.md`
carries it; materializing the same skill twice does not append it twice.

**Mutation** — removing the injection gate must fail the never-injected test;
removing the hot clause must fail the hot test; removing the unlink must fail a
test that a marker consumed in one session does not credit the next.

## What this does not build

**The `skillforge-usage` engine skill.** §9.1's delivery mechanism is not
deferred but replaced. Its job was to reach hot skills, and appending
`MARKER_NOTE` to the materialized body does that at the moment of use, without
a permanent standing-context charge, and without a second artifact to keep in
sync with the protocol wording. Nothing in this design wants a separate engine
skill; if a future signal needs standing context of its own, that is the
argument to revisit, not this one.

**The drift reminder.** §9.1 fires a compliance reminder on detected drift
(injections N turns old with zero scratch writes). It is a corrective for a
failure rate nobody has measured. This slice measures that rate; the reminder
is worth building if it turns out bad.

**ε-holdouts.** The parent spec's own roadmap already places holdout sampling
in v0.3, not v0.2. Beyond sequencing, holdout events are ambiguous at this
scale — a holdout with no fingerprint is equally consistent with "the skill was
valuable," "the task never called for it," and "the fingerprint pattern is too
narrow" — and at single-user volume they never reach per-skill significance
while degrading real sessions to get there. The marker truth table's
fingerprint-without-marker cell is a free, weaker proxy for the same question.

**Turn-accurate ingestion.** §9.1 describes markers as PostToolUse-timestamped.
Reading the file at Stop instead costs turn granularity, which nothing
currently consumes, and saves a file read on every tool call against a <50ms
budget. Moving ingestion into `detect.py` later is a strict addition; it does
not change the crediting rules or the schema.

## Ceilings

**Concurrent sessions in one repo share one marker file.** Two sessions in the
same working tree can cross-credit. The injection gate bounds this to skills
both sessions injected; anything else is dropped. Closing it needs a session
id the model can write, which it does not have.

**The model's cwd and the hook's cwd are assumed equal.** The preamble names a
relative path; the reconciler resolves it against the hook payload's `cwd`. A
model writing from a subdirectory writes a file the reconciler will not find.
Markers are lost, never misattributed, so the failure is silent undercounting
in the direction of no evidence rather than wrong evidence.

**A hot skill applied from its description alone produces no marker.** The
appended note lives in the body, so it arrives only when the body is opened.
This is a thin slice of "used" — a model acting on a one-line description has
not really applied the procedure — but it is not empty, and it is the residue
of choosing the body over standing context.

**Hot skills still have no fingerprint detection.** `needs_fingerprint` returns
False when `injected_ts is None`, and a hot skill never has an injection event,
so the Stop-time diff grep skips it. The marker becomes its *second* signal
alongside Bash command matching, not its second-and-third. Closing this needs
the injection-event problem solved, which is the same ceiling the outcome
attribution design records.

**A read-then-unlink race exists** between the reconciler reading the file and
the model appending to it. Stop fires between turns, when the model is not
writing, so the window is narrow; a lost line costs one marker.

**Compliance is not enforceable.** Models forget protocols and sometimes mark
performatively. That is assumed, not designed against — it is why the passive
layers stay, and why the disagreement rate is recorded rather than the marker
being trusted on its own.
