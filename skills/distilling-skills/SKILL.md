---
name: distilling-skills
description: >
  Distillation procedure for turning the current coding session into a
  reusable SkillForge skill. Use when: /skillforge:learn runs, or the
  user asks to capture/distill/save what was learned this session.
  Do NOT use when: distilling a failure, trap, or debugging dead-end
  (use distilling-failures), or when writing plugin/engine skills by hand.
---

# Distilling a Session into a Skill

Produce one candidate SKILL.md from the current session, get the user's
approval, then save it through the enforced write path. Never write skill
files directly — `save_skill.py` is the only save path (it validates,
secret-scans, and materializes).

## The distillation contract

Work through these in order. Aborting is a success outcome — say why in
one line and stop.

1. **Identify the distillable unit.** One procedure that worked, small
   enough to state as numbered steps. If the session contains several,
   ask the user which one (or use the topic hint from the command).

2. **Novelty self-gate.** Ask honestly: *would a fresh Claude instance
   actually not know this?* If the skill restates model-obvious knowledge
   (standard library usage, common framework patterns, anything you could
   produce without this session), ABORT the save and tell the user why.
   This kills junk saves.

3. **Duplicate check.** List existing skills:
   `ls ~/.claude/skillforge/skills/ 2>/dev/null; ls .claude/skillforge/skills/ 2>/dev/null`
   If an existing skill covers this, propose updating it instead of
   creating a sibling.

4. **Generalize.** Strip project-specific incidentals (paths, names,
   versions) unless the knowledge is genuinely project-specific. Test:
   "would a fresh Claude in a different repo benefit?"

5. **Assign scope.** Mentions repo-specific paths/conventions → `project`;
   otherwise `global`. Tell the user which you chose; they can override.

6. **Answer the one-shot question.** Write the body as what you would
   tell a fresh instance of yourself so it could do this in one pass:
   `## Procedure` (numbered steps), `## Gotchas` (if any), and a
   mandatory `## Verification` (a concrete command or check that proves
   the procedure worked).

7. **Write both trigger directions.** The `description` frontmatter MUST
   contain "Use when:" cases AND "Do NOT use when:" cases. Negative
   triggers fight over-injection; save_skill.py rejects drafts without them.

8. **Emit attribution artifacts.** Add two frontmatter fields:
   `verification.command` — the single machine-runnable command from your
   `## Verification` section (save_skill.py rejects skills without it) —
   and `fingerprints`, a list of 2–3 distinctive code fragments from the
   procedure. Distinctive means it would not appear in unrelated code:
   `express.raw({type: 'application/json'})` qualifies; `npm install`
   does not. These power usage detection; a skill without them is
   invisible to outcome tracking.

9. **Secret scan the draft yourself** before showing it:
   `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/secscan.py" <draft-path>`
   Session transcripts routinely contain keys, tokens, and connection
   strings. Redact hits (replace with `<REDACTED>` placeholders that keep
   the instruction meaningful). save_skill.py scans again regardless.

## Skill format

```markdown
---
name: kebab-case-name
kind: skill
scope: global            # or project
description: >
  One-line summary.
  Use when: <positive triggers>.
  Do NOT use when: <negative triggers>.
verification.command: "<single runnable command from ## Verification>"
fingerprints:
  - "<distinctive fragment 1>"
  - "<distinctive fragment 2>"
provenance:
  repo: <org/repo or local dir name>
  commit: <short sha if in git, else omit>
  distilled: <YYYY-MM-DD>
---

## Procedure
1. ...

## Gotchas
- ...

## Verification
- `<command>` should <observable result>.
```

## Saving

1. Write the draft to the session scratchpad (not the store).
2. Show the full draft to the user and ask for approval. Human-in-the-loop
   at capture is what keeps garbage out — never silent auto-save.
3. On approval:
   `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/save_skill.py" <draft-path> --scope <global|project> [--project-root <repo>]`
   (`--project-root` is the repo root; required in practice for project scope.)
4. Exit 0 → report the two printed paths. Exit 1 → fix the printed
   `REJECTED`/`SECRET BLOCKED` reasons and retry; never hand-copy the file
   into the store to work around a rejection.
