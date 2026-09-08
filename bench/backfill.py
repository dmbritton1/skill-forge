#!/usr/bin/env python3
"""One-shot, idempotent: label historical result rows with `skill_source`.

Rows written before Q1 carry none of the source keys, so a filter on
`skill_source == "authored"` silently excludes the pilot and E1 comparators
that every Q1 claim is read against. A documented read rule would work until
someone forgot it; the register's own lesson is that un-indexed data gets
described from memory and described wrong.

Only `skill_source` is backfilled. `distiller`, `draw` and `skill_path` are
genuinely unknown for a historical row and inventing them would be worse than
their absence. `results-leaky-stub.jsonl` is not backfilled: it is superseded
as an authoring design and only its control rows are live.

Run: python3 bench/backfill.py
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
FILES = ("results.jsonl", "results-round1.jsonl")


def backfill(path):
    """Add `skill_source` to rows lacking it. Returns rows changed."""
    path = Path(path)
    lines = path.read_text(encoding="utf-8").splitlines()
    out, changed = [], 0
    for line in lines:
        if not line.strip():
            continue
        row = json.loads(line)
        if "skill_source" not in row:
            # control installs no skill at all, so "authored" would be a lie.
            row["skill_source"] = None if row.get("arm") == "control" else "authored"
            changed += 1
        out.append(json.dumps(row))
    if changed:
        path.write_text("\n".join(out) + "\n", encoding="utf-8")
    return changed


def main():
    for name in FILES:
        print("%s: %d row(s) labelled" % (name, backfill(ROOT / name)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
