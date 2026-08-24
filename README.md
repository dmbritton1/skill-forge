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
warm and are injected with hedged wording. `trusted` here means repeatedly
verified in real sessions — the parent spec's Tier A conjunct (independent
validation) arrives in slice D.

## Tests

    for t in tests/test_*.py; do python3 "$t" || echo "FAILED $t"; done

Plans and designs live in `docs/superpowers/`. Shipped: v0.1, v0.2 slice A
(ledger, trust, sync), slice B (retrieval, tiering), slice C1 (detection
substrate: symptom triggers, verification capture, fingerprint snapshots),
and slice C2 (Stop/SessionEnd reconciler, confidence buckets). Not yet
built: slice D (Tier A validation, capture suggestions, `/stats`).
