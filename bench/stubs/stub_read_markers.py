#!/usr/bin/env python3
"""E16 candidate F: blank reconcile.read_markers so the model must author it.

The parent commit's own docstring stays, verbatim. It already states the
contract the historical bug broke -- "Untrusted input. Bad lines are skipped
rather than raising" -- and says nothing about which exceptions json.loads can
raise. The bug (fixed in ea4c47f) caught ValueError only, so a deeply nested
line raised RecursionError straight out of the function and cost the whole
Stop's reconciliation. That the promise is stated and was still broken is the
trap under measurement, and the screen may find a fresh model reads it
correctly (E16 spec, threat 1).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _stub import stub_functions


def main():
    try:
        stub_functions("scripts/reconcile.py", ["read_markers"])
    except ValueError as err:
        print("stub: %s" % err, file=sys.stderr)
        return 1
    print("stubbed read_markers")
    return 0


if __name__ == "__main__":
    sys.exit(main())
