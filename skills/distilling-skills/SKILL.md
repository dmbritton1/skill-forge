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

   Two rules decide whether either one is worth anything. Both were learned
   the hard way — every skill in the library failed critique on one of them.

   **The verification must FAIL when the skill is skipped.** "Passes when
   applied" is not the bar; a check that passes either way is not evidence
   of anything. Ask concretely: if someone ignored this procedure entirely,
   would this command still exit 0? If yes, it is not a verification.
   - `grep -q 'Co-Authored-By' .git/COMMIT_EDITMSG` — **no**. That file is
     not cleared between commits, so it still holds the previous commit's
     trailer and passes on any repeat.
   - `python3 tests/test_guard.py` where the suite only checks hooks it
     names — **no**. A brand-new hook that skips both the guard and its test
     leaves the suite green.
   State in `## Verification` what the command does when the procedure was
   NOT followed. If you cannot make it discriminate, say so there plainly
   rather than shipping a check that always passes.

   **Add `provenance.introduced_by` when you can name it.** The commit that
   introduced the behaviour this skill teaches — not `provenance.commit`,
   which is where the repo happened to be when you distilled, i.e. AFTER the
   change. Tier A rewinds to its parent to get a state where the skill has
   genuinely not been applied; without it, validation runs at HEAD, where the
   skill's own verification already passes, and the vacuity gate correctly
   refuses to grade it. `git log -S'<a distinctive fragment>' --reverse`
   usually finds it. Omit it rather than guess: a wrong commit grades a
   working skill `fail`.

   **`provenance.repo` should resolve to a local checkout when it can.**
   Tier A's executable run needs a real repository to work in, and an
   `org/repo` slug is not a path — for a global skill that is the only
   candidate, so a slug leaves it critique-only forever. A project-scoped
   skill is safe either way: its store root is the checkout, and validation
   falls back to that.

   **A fingerprint must be text that ends up IN A FILE.** Matching runs
   against the added lines of `git diff HEAD` plus untracked file contents.
   Anything else is invisible no matter how well the skill was applied:
   commands you run (`git commit -F -`), commit messages
   (`Co-Authored-By: ...`), tag annotations, PR bodies, shell output. If the
   procedure's whole effect is outside the working tree, it has no usable
   fingerprint — say so rather than inventing one, and let
   `verification.command` carry the detection alone.

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
  repo: <path that resolves on this machine, else org/repo>
  introduced_by: <sha where the behaviour landed, omit if unsure>
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
   **Improving a skill that already exists is `--action update`.** A plain
   save now refuses to overwrite, because a same-name save used to clobber
   silently and nothing recorded that a create was really an edit. `update`
   requires the skill to exist, and re-runs critique inline before it returns
   — an edit voids the previous verdict, and the author who made the edit is
   the one who should wait for the replacement rather than leaving the skill
   capped until some later session picks it up. Expect it to block for a
   couple of minutes.

   Add `--decision` naming what the user actually did to the draft, because
   the difference between "took it as written" and "rewrote half of it" is
   the only signal this framework gets about its own distilling:
   - `approved` — saved as you drafted it (the default; omit the flag)
   - `edited` — the user changed the content before approving
   - `scope_overridden` — the user changed `--scope` from what you proposed
   Pass `--decision-reason "<short phrase>"` whenever the user said why.
   Record what happened, not what flatters the draft.
4. Exit 0 → report the two printed paths. Exit 1 → fix the printed
   `REJECTED`/`SECRET BLOCKED` reasons and retry; never hand-copy the file
   into the store to work around a rejection.
