# Outcome attribution — design

**Status:** proposed
**Supersedes nothing.** Amends slice C2's outcome model (`detect.py`'s
verification path) without touching its bucket rule.

## Problem

`detect.py` credits a skill with a `detection` event, carrying a success or
failure outcome, whenever a Bash command pattern-matches that skill's
`verification.command` tokens inside its scope directory. Nothing requires
that the skill was injected, read, or followed.

That outcome is the only input to `success_sessions`, which is the only input
to the organic half of the Tier A conjunct. So the evidence that promotes a
skill to `trusted` — and therefore into every session's context — is
attributed by string match against a command the user may have run for
entirely unrelated reasons.

This is not hypothetical. During the D2 calibration exercise the ledger
recorded a `detection/verification` row for `fix-the-flaky-check`, a skill
written deliberately to be unusable and never read by anything. It matched
because it declared `verification.command: python3 tests/test_ledger.py`, and
that command was run repeatedly while working on the ledger. The rows carried
a null outcome only because this environment does not set the harness's
`is_error` flag; a live PostToolUse payload does, and they would have been
recorded as successes.

Two clean sessions can therefore be earned entirely by commands that would
have been run anyway.

### Why it has not shown up as a bug

The conjunct also requires `critique == pass`, which currently passes nothing.
The strict half masks the loose half: no skill reaches `trusted`, so nobody
observes that the organic evidence would not have meant much if one had. The
two halves fail in opposite directions, and fixing the gate without fixing
attribution would exchange a wall for a rubber stamp.

This is why attribution is sequenced first. It makes promotion *harder* in the
short term, which costs nothing while promotion is already impossible, and it
is a precondition for trusting any measurement taken afterwards — including
the positive control the calibration corpus still lacks.

## The rule

A verification-matched detection is credited to a skill only if that skill was
injected into the same session.

Injection is already recorded. `retrieve.py` writes an `injection` event and
adds the name to the session's state file on a warm prompt match; `detect.py`
does the same for an anti-skill symptom match. The state file is the set of
skills whose text actually reached the model this session, which is exactly
the population entitled to claim credit for what happened next.

## Hot-tier skills are exempt

Hot skills are materialized into the native skills directory and injected by
the harness itself. SkillForge never sees that happen and logs no injection
event, so under the rule above a hot skill would stop earning outcomes
entirely: `last_used` would freeze, the 90-day freshness clause would demote
it to `working`, it would fall to warm, start being injected visibly, earn
successes again, and return to hot. An oscillation driven by nothing but the
attribution rule.

So the rule applies to warm skills only. The reasoning: the confound matters
for *earning* trust, and trust is earned at warm. A hot skill has already
cleared the bar once; letting it retain that status on a weaker signal is a
smaller cost than a promotion loop.

This is a deliberate ceiling, not an oversight. A hot skill's retention still
rests on a matching command rather than on demonstrated use. Closing it needs
the harness to report which native skills it injected, which SkillForge cannot
currently observe.

## Implementation

Three changes, all small.

**1. `sync._write_triggers` — carry the tier.** The verifications entries
currently hold `skill`, `root` and `tokens`. Add `tier`. `sync` already knows
it; `detect.py` cannot otherwise distinguish hot from warm without reading
`index.json`, which would add a file read to every tool call.

**2. `detect.run` — move the state load above the verification loop.** It
already calls `retrieve.load_state(session)` a few lines further down, for the
symptom path. Reading it earlier costs nothing — the same file, the same hook
invocation.

**3. `detect.run` — gate the credit.** In the verification loop, log the
detection only when the skill's tier is `hot`, or its name is in the session's
injected set. Everything else about the loop is unchanged.

Net cost at runtime: zero additional I/O. One additional field in a file that
is already rewritten on every sync.

## Data

Existing rows are left alone and the rule applies forward only. The store is
nearly empty and nothing has reached `trusted`, so there is very little
confounded history to inherit, and marking or deleting old rows would discard
genuine successes alongside spurious ones for no present benefit.

## Testing

The suites may not spawn a model, run a skill-authored command, or create a
worktree; none of this needs any of those.

- A warm skill with no injection this session, whose verification command
  runs and succeeds: no detection row.
- The same skill, injected earlier in the session: one detection row with the
  outcome.
- A hot skill with no injection event: one detection row. This is the
  exemption, and it must be asserted explicitly rather than inherited, or the
  oscillation returns silently the next time the loop is refactored.
- Injection in a *different* session does not credit this one.
- Mutation: removing the gate must fail the first test. Removing the hot
  exemption must fail the third.

## What this does not fix

- **Retention of hot skills** still rests on command matching, per the ceiling
  above.
- **Same-session is still a proxy.** A skill read in one session and applied in
  the next earns nothing. Tightening further would need the model to report
  which skill it actually followed, which nothing currently asks it to do.
- **Nothing yet measures whether injection helps.** `injections` is counted and
  read only by a debug CLI. Correlating injection with session outcome is a
  separate piece of work, and the benchmark that would support it lives on the
  unmerged `claude/project-status-roadmap-4c408a` branch.
- **The critique gate is untouched.** This spec deliberately does not change
  the conjunct. Its purpose is to make the organic half worth trusting so that
  the gate decision can be made against real evidence.
