#!/usr/bin/env python3
"""Rank post-cutoff fix commits by their fitness as author-mode bench traps.

E11 rejected both never-run tasks, leaving the bench one usable trap, so new
tasks have to be written. An author-mode trap needs a real bug, a fix, tests
that were red before it, and -- the binding shape -- a single self-contained
function carrying a docstring contract, because `stub_cmd` blanks that body and
the session authors against the docstring without ever seeing what grades it.

Recency rules nothing out: the cutoff is May 2026 and this repository's whole
history postdates it. Fitness is therefore about shape, scored as: one source
file (3), one or two functions touched (3, or 1 for up to four), new tests
(1 each, capped at 4), a docstring on a touched function (2).

VALIDITY CHECK: 22ddf37 and ab4acfe are the project's two known-good traps. The
ranking is only worth reading if they land near the top; the footer prints where
they fell. If they rank poorly the scoring is wrong, not the commits.

Deterministic, 0 sessions, no model. Run: python3 bench/trap_candidates.py
"""
import re
import subprocess
import sys

KNOWN = {"22ddf37", "ab4acfe"}
SINCE = "2026-08-09"


def sh(cmd):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True).stdout


def candidates():
    log = sh("git log --since=%s --date=short --format='%%h|%%ad|%%s' -- scripts/ tests/" % SINCE)
    rows = []
    for line in log.strip().splitlines():
        sha, date, subj = line.split("|", 2)
        if not subj.startswith("fix"):
            continue
        files = sh("git show --pretty= --name-only %s" % sha).split()
        src = [f for f in files if f.startswith("scripts/") and f.endswith(".py")]
        tst = [f for f in files if f.startswith("tests/")]
        if not src or not tst:
            continue
        diff = sh("git show --pretty= -U0 %s" % sha)
        new_tests = len(re.findall(r"^\+def (test_\w+)", diff, re.M))
        funcs = set(re.findall(r"^@@[^@]*@@\s*def (\w+)", diff, re.M))
        body = sh("git show %s:%s" % (sha, src[0])) if funcs else ""
        doc = sum(1 for fn in funcs if re.search(
            r"^def %s\(.*?\):\n\s+[\"']{3}" % re.escape(fn), body, re.M | re.S))
        score = (3 if len(src) == 1 else 0)
        score += 3 if 1 <= len(funcs) <= 2 else (1 if len(funcs) <= 4 else 0)
        score += min(new_tests, 4) + (2 if doc else 0)
        rows.append((score, sha, date, len(src), len(funcs), new_tests, doc, subj))
    rows.sort(reverse=True)
    return rows


def main():
    rows = candidates()
    print("%-3s %-9s %-11s %-4s %-4s %-5s %-4s %s" %
          ("fit", "sha", "date", "src", "fns", "+test", "doc", "subject"))
    for score, sha, date, ns, nf, nt, doc, subj in rows:
        mark = "  <== KNOWN GOOD" if sha in KNOWN else ""
        print("%-3d %-9s %-11s %-4d %-4d %-5d %-4d %s%s" %
              (score, sha, date, ns, nf, nt, doc, subj[:64], mark))
    print("\ntotal fix-commit candidates: %d" % len(rows))
    rank = {r[1]: i + 1 for i, r in enumerate(rows)}
    for sha in sorted(KNOWN):
        print("known-good %s ranked %s of %d" % (sha, rank.get(sha, "ABSENT"), len(rows)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
