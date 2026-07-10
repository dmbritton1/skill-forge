#!/usr/bin/env python3
"""Blocking secret scan for skill drafts (spec 11.1).

Gitleaks-style pattern rules over candidate skill text. Any hit blocks
the save; the offending lines are printed for redaction. No bypass flag
by design.

Usage: secscan.py FILE...   (exit 0 clean, 1 hits, 2 usage error)
"""
import re
import sys

RULES = [
    ("aws-access-key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("github-token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b")),
    ("stripe-key", re.compile(r"\b[rs]k_(live|test)_[0-9a-zA-Z]{24,}\b")),
    ("slack-token", re.compile(r"\bxox[baprs]-[0-9A-Za-z-]{10,}")),
    ("private-key-block", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.eyJ[A-Za-z0-9_-]{8,}")),
    ("bearer-token", re.compile(r"(?i)\bbearer\s+[A-Za-z0-9_\-.=]{16,}")),
    # user:password@host — plain URLs without credentials don't match
    ("connection-string", re.compile(r"\b[a-z][a-z0-9+.-]*://[^/\s:@]+:[^@\s]+@")),
    # quoted value assigned to a secret-ish name; unquoted prose passes
    ("assigned-secret", re.compile(
        r"(?i)\b(api[_-]?key|secret|token|passwd|password)\b\s*[:=]\s*['\"][^'\"]{8,}['\"]")),
]


def scan_text(text):
    """Return [(lineno, rule_name, stripped_line)] for every rule hit."""
    hits = []
    for lineno, line in enumerate(text.splitlines(), 1):
        for name, rx in RULES:
            if rx.search(line):
                hits.append((lineno, name, line.strip()))
    return hits


def main(paths):
    failed = False
    for path in paths:
        with open(path, encoding="utf-8", errors="replace") as f:
            text = f.read()
        for lineno, rule, line in scan_text(text):
            print("%s:%d: %s: %s" % (path, lineno, rule, line))
            failed = True
    return 1 if failed else 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: secscan.py FILE...", file=sys.stderr)
        sys.exit(2)
    sys.exit(main(sys.argv[1:]))
