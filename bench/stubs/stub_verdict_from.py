#!/usr/bin/env python3
"""E13 trap C: blank validate.verdict_from so the model must author it.

The parent commit's own docstring stays, verbatim. It says a criterion must
quote "the skill text" as "a verbatim span". An implementer who takes that
literally writes an exact substring match, which is the historical bug fixed in
c0d7d88: a critic re-wraps quotes across lines. It is also silent on measuring
the evidence floor on the raw span, the second trap. Nothing is added to it.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _stub import stub_functions


def main():
    try:
        stub_functions("scripts/validate.py", ["verdict_from"])
    except ValueError as err:
        print("stub: %s" % err, file=sys.stderr)
        return 1
    print("stubbed verdict_from")
    return 0


if __name__ == "__main__":
    sys.exit(main())
