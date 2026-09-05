#!/usr/bin/env python3
"""Did the last commit carry the project's Co-Authored-By trailer?

The `commit-trailer` skill's verification. Two conjuncts, because neither
alone fails when the procedure is skipped:

  - HEAD's message carries the trailer. Reads the commit, not
    `.git/COMMIT_EDITMSG`, which is git's editor scratch file: after a commit
    rejected by a hook that file holds the attempted message while HEAD never
    moved.
  - the index is clean. The skill's precondition is that there ARE staged
    changes and the procedure ends by committing them, so a dirty index means
    no commit happened -- and without this the message check reads the
    PREVIOUS commit, which may well carry the trailer, and passes with the
    procedure skipped entirely.

Deliberately NOT named test_*.py: it asserts on live repository state, so the
suite runner (`tests/test_*.py`) must not collect it. It is a checker, run by
Tier A validation and by hand, not a unit test.

A single argv on purpose. validate.verification_argv refuses shell
metacharacters outright, treating skill text as attacker-controlled, so the
`&&` and `$(...)` this replaces made the skill permanently ineligible for an
executable run -- which is the only route to `trusted` a project-scoped skill
has.

Run: python3 tests/check_commit_trailer.py
"""
import subprocess
import sys

TRAILER = "Co-Authored-By: Claude Opus 5"


def git(*args):
    return subprocess.run(["git"] + list(args), stdout=subprocess.PIPE,
                          stderr=subprocess.DEVNULL, text=True)


def main():
    staged = git("diff", "--cached", "--name-only")
    if staged.returncode != 0:
        print("not a git repository, or git failed")
        return 1
    if staged.stdout.strip():
        print("index is not clean: %d path(s) still staged, so the commit "
              "this checks for has not happened yet"
              % len(staged.stdout.strip().splitlines()))
        return 1
    head = git("log", "-1", "--format=%B")
    if head.returncode != 0:
        print("no commits yet")
        return 1
    if TRAILER not in head.stdout:
        print("HEAD's message does not carry %r" % TRAILER)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
