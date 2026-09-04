#!/usr/bin/env python3
"""Blank out retrieve.fingerprint_preexisting so the model must author it.

The replacement docstring states the CONTRACT only. It names the three return
values and the work bounds, because both are real API facts the caller
depends on -- but it deliberately does NOT say what to do when a bound
actually bites. That inference (a capped search that finds nothing has not
proved absence) is exactly the knowledge under measurement.

The unknown-causes list mirrors the original C1 design doc verbatim -- "not a
git repo, git missing, or the subprocess timeout fired" -- which is what the
human author had in front of them when the bug was originally written. The
task therefore reproduces the historical condition rather than an easier or
harder one.
"""
import re
import sys
from pathlib import Path

STUB = '''def fingerprint_preexisting(fingerprints, cwd):
    """Was any of these fingerprints already in the repo at `cwd`?

    `fingerprints` is a list of pre-tokenized patterns (each a list of
    tokens, as produced by patterns.tokenize). Use `git grep` to narrow to
    candidate files, then patterns.matches() to confirm a candidate really
    contains the pattern.

    Returns 1 if any fingerprint is already present, 0 if none are, and None
    when the answer is unknown (not a git repo, git missing, or the
    subprocess timeout fired).

    This runs inside a blocking hook, so bound the work: pass
    GIT_TIMEOUT_S as the subprocess timeout, examine at most
    SNAPSHOT_MAX_FILES of the candidate files git reports, and read at most
    SNAPSHOT_MAX_BYTES from any one file.
    """
    raise NotImplementedError("implement me")
'''


def main():
    p = Path("scripts/retrieve.py")
    src = p.read_text(encoding="utf-8")
    m = re.search(r"^def fingerprint_preexisting\(fingerprints, cwd\):\n(?:.*\n)*?(?=^def |\Z)",
                  src, re.M)
    if not m:
        print("stub: fingerprint_preexisting not found", file=sys.stderr)
        return 1
    p.write_text(src[:m.start()] + STUB + "\n" + src[m.end():], encoding="utf-8")
    if "NotImplementedError" not in p.read_text(encoding="utf-8"):
        print("stub: replacement did not take", file=sys.stderr)
        return 1
    print("stubbed fingerprint_preexisting")
    return 0


if __name__ == "__main__":
    sys.exit(main())
