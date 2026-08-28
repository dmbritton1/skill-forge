# SkillForge

A self-improving skill library for Claude Code, v0.1. Distills coding
sessions into reusable skills (`/skillforge:learn`) and debugging
dead-ends into anti-skills (`/skillforge:learn-failure`), blocks secrets
on every save, and materializes skills where Claude Code loads them.

Engine (this plugin) and knowledge (learned skills) are separate:

- Global store: `~/.claude/skillforge/{skills,antiskills}/<name>/SKILL.md`
- Project store: `<repo>/.claude/skillforge/{skills,antiskills}/<name>/SKILL.md`
- Native copies: `~/.claude/skills/skillforge-hot/` (global) or
  `<repo>/.claude/skills/skillforge-hot/` (project)

## Install

    claude plugin marketplace add /Users/dwightbritton/Developer/skill-forge
    claude plugin install skillforge@skillforge

Installing copies the tree into `~/.claude/plugins/cache/`, so edits to this
repo do not reach a running session until the copy is refreshed:

    claude plugin uninstall skillforge@skillforge
    claude plugin install skillforge@skillforge --yes

`plugin update` looks like the right command and is not: it compares the
`version` in `plugin.json` and reports "already at the latest version" without
re-copying, so source edits under an unchanged version are silently ignored.
Bumping the version works too; reinstalling is the reliable habit. Both forms
need the qualified `skillforge@skillforge` id — the bare name is not found.

`--plugin-dir <repo>` loads the working tree directly and skips that copy, but
it only affects `claude` processes you launch yourself. The desktop app spawns
its own and never reads a shell profile, so an alias carrying the flag has no
effect there — a real install is the only path that covers both.

Keep the repo off iCloud Drive. `~/Desktop` and `~/Documents` are synced by
default, and every read there goes through the iCloud file provider: installing
from a synced folder walks the whole tree and fails with `ETIMEDOUT`. The same
tree installs in about a second from local storage.

## Usage

- `/skillforge:learn [optional topic hint]` — distill the current session
  into a skill. Shows a draft for approval, then saves.
- `/skillforge:learn-failure [optional topic hint]` — distill a debugging
  trap into an anti-skill (Trap/Symptom/Cause/Fix format).
- `/skillforge:review` — review and approve quarantined skills (anything
  pulled or modified outside the save path). Untrusted skills are never
  loaded natively until approved.
- `/skillforge:find <topic>` — search the whole library (hot + warm) and
  pull anything the automatic paths didn't surface.

Trust model (v0.2): every skill's content hash is registered in a local,
never-committed `~/.claude/skillforge/trust.json` (self-saves auto-trust).
A SessionStart hook syncs native copies from the store: trusted skills are
materialized, unknown/modified ones are evicted and flagged for review.
Usage and review events land in `~/.claude/skillforge/ledger.db`.

Delivery tiers (v0.2): trusted skills compete for a fixed hot budget
(1,500 description-tokens) ranked by usage — winners are materialized as
native skills; the rest stay warm in a BM25 retrieval index and are
injected per-prompt by a UserPromptSubmit hook (max 3 skills, 1,200-token
budget, session dedupe, two-matched-terms minimum; anti-skills bypass the
count cap). Everything injected is logged to the ledger.

Detection (v0.2 slice C1): anti-skills are never hot — they carry
`symptoms:` frontmatter compiled into a trigger index, and a PostToolUse
hook matches tool output against it, injecting the matching anti-skill the
moment its error signature appears. The same hook matches Bash commands
against skills' `verification.command`, which is the strongest usage signal
in the system. Matching is token-based, not regex: quoting, whitespace, and
inserted arguments never decide a match. Every injection — prompt-triggered
or symptom-triggered — also records whether the skill's fingerprints were
already in the repo, so a later reconciler can tell "the model applied
this" from "it was already there."

Outcome interpretation (v0.2 slice C2): a reconciler hook runs at the end
of every turn (Stop) and at session end (SessionEnd), reading the current
session's ledger rows and closing them out — crediting a skill as used
when its fingerprint shows up in `git diff HEAD` plus untracked files, and
issuing success/failure verdicts for anti-skills based on whether their
symptom fired again within a time window. It costs one ledger read when
nothing is pending, holds no state of its own, and derives every verdict
from the ledger, so re-running it is idempotent. From these events, each
skill's confidence is one of three buckets — `unproven`, `working`, or
`trusted` — counted in distinct sessions rather than raw events, with a
90-day decay that drops a stale `trusted` back to `working`. Only
`working`-or-better skills compete for the hot tier; `unproven` skills stay
warm and are injected with hedged wording. Real-session verification is one
half of what `trusted` requires — see "Tier A validation" below for the
other half, the parent spec's independent-validation conjunct.

## Automatic capture

You do not have to remember `/skillforge:learn`. When a command fails twice
in a row and then succeeds, SkillForge treats that as a lesson worth
keeping: it drafts a skill from that stretch of the session in a background
process, and interrupts with the finished draft the moment it is ready. You
approve it or discard it — nothing is ever saved silently.

- **What triggers it:** two consecutive failures on the same command,
  followed by a success. A test that passes on the first retry is not a
  struggle and drafts nothing.
- **What it costs:** one `claude -p` call per signal, in a detached process.
  Your session never waits on it. Billed against your subscription, unless
  `ANTHROPIC_API_KEY` is set in your environment — the drafter inherits it
  like any other `claude` invocation, and `--safe-mode` does not change
  that. Override the model with `SKILLFORGE_DRAFT_MODEL` (default `sonnet`).
- **Where drafts live:** `~/.claude/skillforge/drafts/`. Discarding one
  deletes the file but remembers that you discarded it, so a repeat proposal
  for the same command says so.
- **Duplicates:** a draft that closely restates a skill you already have is
  dropped without bothering you.

The drafter runs with `--safe-mode`, which disables hooks in the child
process — SkillForge cannot trigger itself — while keeping your
subscription login. `--bare` would also disable hooks but forces an API
key, which is why it is not used.

## Tier A validation

v0.2 slice D2 adds independent validation on top of what real sessions show.
`trusted` no longer means only "it worked twice" — it means a passing
**critique** (a fresh model turn, given only the skill's text and nothing
from the session that produced it, judges whether the procedure is
followable, its preconditions are stated, and its verification is actually
checkable), plus either two clean real-session uses or a passing
**executable** run. A `fail` on critique blocks `trusted` outright, by
either route. Editing a skill's text always voids its prior verdicts,
critique included — the new text has earned nothing yet, and needs a fresh
critique before it can count toward `trusted` again.

- **Critique** runs automatically, in the background, every time a skill is
  saved through `/skillforge:learn` or a draft approval. It costs one model
  turn and nothing you wait on.
- **Executable** validation goes further: a throwaway checkout of the
  skill's own repo, a fresh model instance following the procedure with none
  of the current session's context, then the skill's own
  `verification.command` run before and after. A pass here — or two clean
  real sessions with no failures — is the second half of `trusted`,
  alongside a passing critique. A `fail` here withholds only the executable
  route; the skill can still reach `trusted` the organic way, through two
  clean sessions, once critique has passed. At most one executable run is
  scheduled per session.
- **Anti-skills are never executable-validated.** They document a trap, not
  a runnable procedure, so they carry no `verification.command` — critique
  is the only Tier A check that ever runs against one.

Approving a skill in `/skillforge:review` does more than trust its text: it
also permits SkillForge to *run* that skill's `verification.command`
unattended, in a throwaway git worktree, the next time executable validation
picks it. Only approve a skill whose command you would be willing to run
yourself. **This is not a network sandbox** — the run has no shell and
happens in a scratch checkout, but it inherits your normal network access
(there is no portable way to change that within this project's
stdlib-only, Python 3.9 constraint). Treat approval as "I'd run this
command myself," not "this is isolated."

Executable validation is opportunistic, not universal: it only runs when a
skill's `provenance.repo` resolves to a real local directory holding that
skill's git repo. Today's distiller records `provenance.repo` as a name
(an `org/repo`-style string, not a filesystem path) for every skill it
captures, so for most real skills executable validation cannot run at all —
it sits out silently rather than failing. Those skills still reach
`trusted` the way v0.1 always allowed: a passing critique plus two clean
real-session uses, no failures, within the last 90 days. Nobody should
expect executable validation to be running just because a skill looks
otherwise well-formed.

`/skillforge:library` shows both verdicts (`pass`, `fail`, or blank if never
run) alongside the bucket they feed into.

## Reviewing what you have

`/skillforge:library` lists every saved skill with the confidence it has
earned: `unproven` (no real session has verified it), `working` (at least
one real session has, but `trusted`'s other requirements aren't both met
yet), `trusted` (a passing critique, plus either two clean real sessions
or a passing executable run, used within 90 days — see "Tier A validation"
above). It also shows the two Tier A verdicts (`pass`, `fail`, or blank if
never run) per skill. It will show any skill in full, and delete one on
request. Deleting a skill leaves its ledger history intact, so re-saving
the same name starts from `unproven` rather than silently inheriting an
old bucket.

## Tests

    for t in tests/test_*.py; do python3 "$t" || echo "FAILED $t"; done

Plans and designs live in `docs/superpowers/`. Shipped: v0.1, v0.2 slice A
(ledger, trust, sync), slice B (retrieval, tiering), slice C1 (detection
substrate: symptom triggers, verification capture, fingerprint snapshots),
slice C2 (Stop/SessionEnd reconciler, confidence buckets), slice D1
(automatic capture), and slice D2 (Tier A validation). Not yet built:
`/stats` — `/skillforge:library` is a library view, not an analytics
surface.
