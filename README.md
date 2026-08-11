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

## Install (local development)

    claude --plugin-dir /Users/dwightbritton/Desktop/skill-forge

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
budget, session dedupe, two-matched-terms minimum). Everything injected is
logged to the ledger.

Detection (v0.2 slice C1): anti-skills are never hot — they carry
`symptoms:` frontmatter compiled into a trigger index, and a PostToolUse
hook matches tool output against it, injecting the matching anti-skill the
moment its error signature appears. The same hook matches Bash commands
against skills' `verification.command`, which is the strongest usage signal
in the system. Matching is token-based, not regex: quoting, whitespace, and
inserted arguments never decide a match. Every injection also records
whether the skill's fingerprints were already in the repo, so a later
reconciler can tell "the model applied this" from "it was already there."

## Tests

    for t in tests/test_*.py; do python3 "$t" || echo "FAILED $t"; done

Plans and designs live in `docs/superpowers/`. Shipped: v0.1, v0.2 slice A
(ledger, trust, sync) and slice B (retrieval, tiering). Not yet built:
slice C (outcome tracking, confidence buckets) and slice D (Tier A
validation, capture suggestions, `/stats`).
