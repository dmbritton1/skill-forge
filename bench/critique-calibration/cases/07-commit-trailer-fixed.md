---
name: commit-trailer
kind: skill
scope: project
description: >
  End a new commit's message in this repository with the project's
  Co-Authored-By trailer.
  Use when: writing the message for a new commit in skill-forge.
  Do NOT use when: amending a commit, committing in another repository, or
  writing a tag annotation or pull request body — none of those carry this
  trailer.
verification.command: "grep -q 'Co-Authored-By: Claude Opus 5' .git/COMMIT_EDITMSG"
fingerprints:
  - "Co-Authored-By: Claude Opus 5"
  - "git commit -F -"
provenance:
  repo: dmbritton1/skill-forge
  commit: 99b0023
  distilled: 2026-08-29
---

## Procedure

1. Compose the message with the subject, a blank line, the body, a blank
   line, and this as its final line:

       Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>

2. Commit by feeding that message on stdin, which preserves the blank lines
   that `-m` would collapse:

       git commit -F - <<'EOF'
       subject line

       body

       Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
       EOF

## Preconditions

- The working directory is the root of the skill-forge repository and there
  are staged changes to commit.
- `git` and `grep` are on PATH.

## Verification

- `grep -q 'Co-Authored-By: Claude Opus 5' .git/COMMIT_EDITMSG` exits 0.

  Git writes the message of the commit it just made to `.git/COMMIT_EDITMSG`,
  so this reads back your own commit. Run on the same repository before
  step 1 it exits 1, because the previous message has no such line; run
  after step 2 it exits 0. The single quotes keep the whole trailer as one
  grep pattern; without them the shell would split it on spaces.
