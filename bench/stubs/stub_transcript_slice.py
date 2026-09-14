#!/usr/bin/env python3
"""E13 trap D: blank draft.transcript_slice so the model must author it.

The parent commit's own docstring stays, verbatim. It already says the tail
fallback is for a transcript whose entries carry no parseable stamp. The
historical bug (fixed in 521f609) fell back whenever the window matched
nothing, handing the drafter an unrelated slice of session. That the rule is
stated and was still broken is exactly the trap under measurement, and the
screen may find a fresh model reads it correctly (E13 spec, threat 3).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _stub import stub_functions


def main():
    try:
        stub_functions("scripts/draft.py", ["transcript_slice"])
    except ValueError as err:
        print("stub: %s" % err, file=sys.stderr)
        return 1
    print("stubbed transcript_slice")
    return 0


if __name__ == "__main__":
    sys.exit(main())
