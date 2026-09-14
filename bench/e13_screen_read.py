#!/usr/bin/env python3
"""Read E13's control screen in the order its spec fixes: the reference, then the candidates.

docs/superpowers/specs/2026-09-13-e13-author-traps-design.md, section 3.

Written before any screen row existed, because E12's first read went wrong by
hand. A session refused at the session limit postpones the whole screen, and
it is never read around. The reference is read before any candidate. While the
reference is void or incomplete, no candidate is read at all.

Rows are selected with --window FROM TO, exactly as in bench/e12_read.py
(FROM exclusive, TO inclusive, "-" for open), and the flag is repeatable.

Deterministic, 0 sessions. Run:

    python3 bench/e13_screen_read.py --window <SCREEN_START> -
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from e12_read import select  # noqa: E402  -- one window rule, not two

CANDIDATES = ("sf-author-verdict-from", "sf-author-transcript-slice", "sf-author-store-dir")
REFERENCE = "sf-author-fingerprint-preexisting"
N_CANDIDATE = 6
N_REFERENCE = 3
LIMIT_MARK = "session limit"


def _cell(control, task, needed):
    rows = [r for r in control if r.get("task") == task]
    valid = [r for r in rows if r.get("session_ok")]
    return {"valid": len(valid), "needed": needed,
            "resolved": sum(1 for r in valid if r.get("resolved")),
            "rerun": len(rows) - len(valid)}


def read_screen(rows):
    control = [r for r in rows if r.get("arm") == "control"]
    if any(not r.get("session_ok") and LIMIT_MARK in (r.get("session_tail") or "")
           for r in control):
        return {"screen": "postponed", "cells": {},
                "reason": "a session hit the session limit: re-run the whole screen "
                          "as one fresh batch (spec section 3)"}
    ref = _cell(control, REFERENCE, N_REFERENCE)
    out = {"cells": {REFERENCE: ref}}
    if ref["resolved"]:
        out.update(screen="void",
                   reason="the reference resolved, so the environment moved (spec section 3)")
        return out
    if ref["valid"] < N_REFERENCE:
        out.update(screen="incomplete",
                   reason="the reference is not fully measured, so no candidate is read yet")
        return out
    present = [t for t in CANDIDATES if any(r.get("task") == t for r in control)]
    for task in present:
        cell = _cell(control, task, N_CANDIDATE)
        cell["verdict"] = ("rejected" if cell["resolved"] else
                           "incomplete" if cell["valid"] < N_CANDIDATE else "admitted")
        out["cells"][task] = cell
    done = bool(present) and all(out["cells"][t]["verdict"] != "incomplete" for t in present)
    out.update(screen="complete" if done else "incomplete",
               reason="" if done else "a candidate is not fully measured, or none was screened")
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--window", nargs=2, action="append", required=True,
                    metavar=("FROM", "TO"))
    args = ap.parse_args(argv)
    rows = [json.loads(line) for line in
            (ROOT / "results.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    res = read_screen(select(rows, args.window))
    print("screen: %s%s" % (res["screen"], " -- " + res["reason"] if res["reason"] else ""))
    for task, c in res["cells"].items():
        role = "reference" if task == REFERENCE else "candidate"
        print("  %-9s %-36s valid %d/%d  resolved %d  re-run %d  %s"
              % (role, task, c["valid"], c["needed"], c["resolved"], c["rerun"],
                 c.get("verdict", "")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
