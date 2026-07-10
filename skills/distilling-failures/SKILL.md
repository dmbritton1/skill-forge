---
name: distilling-failures
description: >
  Anti-skill extraction: distill a debugging dead-end, trap, or corrected
  mistake from the current session into a SkillForge anti-skill.
  Use when: /skillforge:learn-failure runs, or the user asks to capture a
  gotcha/trap/failure so it never costs time again.
  Do NOT use when: distilling a successful procedure (use
  distilling-skills), or when the failure was a one-off typo with no
  reusable lesson.
---

# Distilling a Failure into an Anti-skill

Anti-skills document the trap, not a procedure. They are often
higher-value per token than success skills: short, and the downside of a
miss is a repeated multi-hour debugging pit.

## Procedure

1. **Find the trap.** Locate the point in the session where time was lost:
   what looked correct but wasn't? What was suspected first (wrongly)?
   Estimate the time cost from the transcript.

2. **Novelty self-gate.** Would a fresh Claude fall into this trap? If the
   mistake was a one-off (typo, stale cache, misread) with no reusable
   lesson, ABORT and say so.

3. **Duplicate check.**
   `ls ~/.claude/skillforge/antiskills/ 2>/dev/null; ls .claude/skillforge/antiskills/ 2>/dev/null`
   Existing anti-skill for this trap → propose updating it.

4. **Write the Symptom for a machine, not a narrator.** The Symptom
   section should lead with the literal error text or signature someone
   would see (exception name, error message fragment), then the misleading
   part — what it makes you wrongly suspect. In v0.2 this field becomes a
   machine-matchable trigger, so specificity matters: never a bare
   "Error" or a single common word.

5. **Assign scope** (same heuristic as skills: repo-specific → project,
   else global), **secret-scan the draft**
   (`python3 "${CLAUDE_PLUGIN_ROOT}/scripts/secscan.py" <draft-path>`),
   and redact any hits.

## Anti-skill format

All four of Trap/Symptom/Cause/Fix are mandatory — save_skill.py rejects
drafts missing any of them.

```markdown
---
name: kebab-case-name
kind: antiskill
scope: global            # or project
description: >
  One-line summary of the trap.
  Use when: <symptom or situation that should trigger this>.
  Do NOT use when: <situations that look similar but aren't this trap>.
provenance:
  repo: <org/repo or local dir name>
  distilled: <YYYY-MM-DD>
---

## Trap
What looked correct but silently breaks things.

## Symptom
The literal error/signature observed, and what it wrongly makes you suspect.

## Cause
The actual mechanism.

## Fix
The correction, concretely (code fragment if short).

## Cost of rediscovery
~<N> min (observed in source session)
```

## Saving

Identical to distilling-skills: draft in the scratchpad, show the user,
on approval run
`python3 "${CLAUDE_PLUGIN_ROOT}/scripts/save_skill.py" <draft-path> --scope <global|project> [--project-root <repo>]`
and report the printed paths; on exit 1 fix the printed reasons and retry.
Never write into the store directly.
