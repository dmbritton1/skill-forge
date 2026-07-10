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

## Tests

    python3 tests/test_secscan.py
    python3 tests/test_save_skill.py

v0.1 scope: no hooks, no ledger, no retrieval — see
`docs/superpowers/plans/2026-07-09-skillforge-v0.1.md`.
