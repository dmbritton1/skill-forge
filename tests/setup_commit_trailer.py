#!/usr/bin/env python3
"""Stage a trivial change, so there is something to commit.

`commit-trailer`'s precondition is that there ARE staged changes; a Tier A
worktree is clean, so a fresh instance following that skill has nothing to
do and the run reports no changes forever. This establishes the state the
procedure assumes -- bench/run.py's `stub_cmd` by another name.

Deliberately NOT named test_*.py: it mutates the working tree, so the suite
runner (`tests/test_*.py`) must not collect it.

Run: python3 tests/setup_commit_trailer.py
"""
import subprocess
import sys
from pathlib import Path

MARKER = "skillforge-precondition.txt"


def main():
    target = Path(MARKER)
    try:
        target.write_text("staged by tests/setup_commit_trailer.py\n",
                          encoding="utf-8")
    except OSError as err:
        print("could not write %s: %s" % (MARKER, err))
        return 1
    r = subprocess.run(["git", "add", "--", MARKER],
                       stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                       text=True)
    if r.returncode != 0:
        print("git add failed: %s" % (r.stderr or "").strip())
        return 1
    # Prove the postcondition rather than assuming it: the whole point is
    # that the index is non-empty when the follow-run starts.
    staged = subprocess.run(["git", "diff", "--cached", "--name-only"],
                            stdout=subprocess.PIPE, text=True)
    if MARKER not in (staged.stdout or ""):
        print("%s is not staged after git add" % MARKER)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
