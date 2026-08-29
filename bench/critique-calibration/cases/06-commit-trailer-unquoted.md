---
name: commit-trailer
kind: skill
scope: project
description: >
  End every commit message in this repository with the project's
  Co-Authored-By trailer.
  Use when: writing a commit message, or amending one, in skill-forge.
  Do NOT use when: committing in any other repository, or writing a tag
  annotation or a pull request body, none of which carry this trailer.
verification.command: "grep -q Co-Authored-By: Claude Opus 5 <noreply@anthropic.com> .git/COMMIT_EDITMSG"
fingerprints:
  - "Co-Authored-By: Claude Opus 5"
  - "git commit -F -"
provenance:
  repo: dmbritton1/skill-forge
  commit: 99b0023
  distilled: 2026-08-29
---

## Procedure

1. Write the commit subject and body as normal.

2. Add one blank line, then this line, as the final line of the message:

       Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>

3. Commit with a heredoc rather than `-m`, so the blank line and the
   trailer survive intact:

       git commit -F - <<'EOF'
       subject line

       body

       Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
       EOF

## Verification

- `grep -q Co-Authored-By: Claude Opus 5 <noreply@anthropic.com> .git/COMMIT_EDITMSG`
  exits 0.

  Git writes the message it just committed to `.git/COMMIT_EDITMSG`, so this
  reads back the commit you actually made. It exits 1 before step 2 is done
  and 0 after, on the same working tree, which is what makes it a check on
  the procedure rather than on the repository.
