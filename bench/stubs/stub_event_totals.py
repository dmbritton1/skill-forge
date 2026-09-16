#!/usr/bin/env python3
"""E16 candidate G: blank ledger.event_totals so the model must author it.

The parent commit's own docstring stays, verbatim. It already states the
distinction the historical bug broke -- a NULL verification outcome is its own
`unknown`, never folded away -- and says nothing about how the rows that map to
that bucket combine. The bug (fixed in 58ce279) assigned instead of adding, so
SQL's separate NULL and '' groups clobbered each other and `unknown` reported
the last group's count rather than the sum. That the bucket is named and the
fold was still wrong is the trap under measurement, and the screen may find a
fresh model reads it correctly (E16 spec, threat 1).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _stub import stub_functions


def main():
    try:
        stub_functions("scripts/ledger.py", ["event_totals"])
    except ValueError as err:
        print("stub: %s" % err, file=sys.stderr)
        return 1
    print("stubbed event_totals")
    return 0


if __name__ == "__main__":
    sys.exit(main())
