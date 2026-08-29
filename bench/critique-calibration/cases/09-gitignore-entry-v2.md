---
name: gitignore-entry
kind: skill
scope: project
description: >
  Stop git from tracking a generated directory by adding it to the
  repository's .gitignore.
  Use when: a build or tool writes a directory of generated files into the
  working tree and `git status` starts listing them.
  Do NOT use when: the files are already tracked by git — ignoring a tracked
  path has no effect, and un-tracking it is a different procedure.
verification.command: "git check-ignore -q build/"
fingerprints:
  - "git check-ignore -q"
  - "core.excludesFile"
provenance:
  repo: dmbritton1/skill-forge
  commit: 99b0023
  distilled: 2026-08-29
---

## Procedure

Throughout, `build/` stands for the directory you are ignoring. Substitute
your own path everywhere it appears, including in the verification command.

1. Confirm `git check-ignore -q build/` exits 1 right now. If it exits 0 the
   path is already ignored by some other rule and there is nothing to do.

2. Open `.gitignore` at the repository root and add `build/` on its own
   line, with the trailing slash so it matches a directory rather than a
   file. Add the line by editing the file rather than appending with `>>`,
   which joins onto the last line when that line has no newline of its own.

## Preconditions

- The working directory is the repository root. `.gitignore` and the ignored
  path are both interpreted relative to it, so run `git rev-parse
  --show-toplevel` and `cd` there first if you are not sure.
- `git` is on PATH, and the directory is untracked. Ignoring an already
  tracked path has no effect.

## Verification

- `git check-ignore -q build/` exits 0.

  `git check-ignore -q` exits 0 when some ignore rule matches the path and 1
  when none does, and it re-reads the ignore rules on every invocation. Step
  1 establishes that it exits 1 before the edit; this establishes that it
  exits 0 after. Comparing the two is what makes it a check on your edit
  rather than on rules that were already present.
