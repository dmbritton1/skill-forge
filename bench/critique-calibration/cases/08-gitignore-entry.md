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
  - "echo build/ >> .gitignore"
provenance:
  repo: dmbritton1/skill-forge
  commit: 99b0023
  distilled: 2026-08-29
---

## Procedure

1. Append the directory's path to `.gitignore` at the repository root, with
   a trailing slash so it matches a directory rather than a file:

       echo 'build/' >> .gitignore

2. Substitute your own directory for `build/` in both that line and the
   verification command below.

## Preconditions

- The working directory is the repository root, so `.gitignore` and the
  path being ignored are both relative to it.
- `git` is on PATH and the directory is untracked. `git status` listing the
  files is what confirms that.

## Verification

- `git check-ignore -q build/` exits 0.

  `git check-ignore -q` exits 1 when the path is not ignored and 0 when some
  pattern matches it, and it consults `.gitignore` on every invocation rather
  than any cached state. Run before step 1 it exits 1; run after step 1 it
  exits 0, on the same working tree.
