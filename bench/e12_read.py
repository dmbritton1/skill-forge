#!/usr/bin/env python3
"""Read E12 in the order its spec fixes: validity (4.2) first, criterion (4.1) second.

docs/superpowers/specs/2026-09-13-e12-irrelevant-injection-harm-design.md

This exists because the first read was wrong. An ad-hoc check compared 6
resolved control sessions against a threshold written for 12 and called the
batch void, when the batch had simply hit the session limit and half its
control was never measured. Spec 4.2 (clarified) evaluates control on a
COMPLETE cell; an unfinished cell is 4.3's business -- postponed, not void.

The criterion is not printed until every cell is complete, control holds, and
every treatment row received its skill. An incomplete batch shows valid counts
per cell and no outcomes.

Rows are selected by --window FROM TO (FROM exclusive, TO inclusive, "-" for
open), repeatable, so one reader serves either re-run shape: one window for a
fresh 36-session batch, two for a first attempt plus a re-run of what was
missing.

Deterministic, 0 sessions. Run:

    python3 bench/e12_read.py --window 2026-09-13T15:33:34 -
"""
import argparse
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TASKS = ("sf-escaping-breaks-symptom-match", "sf-truncation-reports-absent")
IRRELEVANT = "arrow-tzinfo-string-trap"
N_PER_CELL = 6
CONTROL_FLOOR = 10          # of 12 pooled, spec 4.2
HARM_AT = 3                 # of 12 below control, spec 4.1
NO_LARGE_HARM_WITHIN = 1    # of 12, spec 4.1
# Excluded by construction (spec 4.3). Named here as well as by the window so
# a badly chosen window cannot let it in as an extra arm-I row.
SMOKE_TS = "2026-09-13T15:33:34"


def arm_of(r):
    if r.get("arm") == "control":
        return "C"
    return "I" if _stem(r) == IRRELEVANT else "R"


def _stem(r):
    return (r.get("skill_path") or "").rsplit("/", 1)[-1].replace(".md", "")


def _delivered(r):
    return _stem(r) in [i.get("skill") for i in (r.get("injections") or [])]


def _valid(rows):
    return [r for r in rows if r.get("session_ok") and r.get("ts") != SMOKE_TS]


def validity(rows):
    """Spec 4.2, evaluated only where it has something to evaluate."""
    valid = _valid(rows)
    incomplete = []
    for task in TASKS:
        for arm in ("R", "I", "C"):
            n = sum(1 for r in valid if r.get("task") == task and arm_of(r) == arm)
            if n < N_PER_CELL:
                incomplete.append((task, arm, n))
    ctl = [r for r in valid if arm_of(r) == "C"]
    if any(arm == "C" for _, arm, _ in incomplete):
        control = "incomplete"          # 4.3: postponed, never void
    elif sum(1 for r in ctl if r.get("resolved")) < CONTROL_FLOOR:
        control = "void"
    else:
        control = "holds"
    return {"control": control,
            "control_valid": len(ctl),
            "incomplete_cells": incomplete,
            "undelivered": [r for r in valid if arm_of(r) != "C" and not _delivered(r)]}


def criterion(rows):
    """Spec 4.1, pooled across both tasks. Read only after validity() is clean:
    the below-control arithmetic assumes 12 sessions in every arm."""
    scored = [r for r in _valid(rows) if arm_of(r) == "C" or _delivered(r)]

    def tally(arm):
        cell = [r for r in scored if arm_of(r) == arm]
        return sum(1 for r in cell if r.get("resolved")), len(cell)

    c_k, c_n = tally("C")
    out = {"C": {"resolved": c_k, "n": c_n}}
    for arm in ("R", "I"):
        k, n = tally(arm)
        below = c_k - k
        verdict = ("harm" if below >= HARM_AT else
                   "no large harm" if below <= NO_LARGE_HARM_WITHIN else "ambiguous")
        out[arm] = {"resolved": k, "n": n, "below_control": below,
                    "verdict": verdict, "p": fisher(c_k, c_n, k, n)}
    return out


def fisher(a_k, a_n, b_k, b_n):
    """Two-sided Fisher's exact p for a_k/a_n versus b_k/b_n.

    A reported statistic, not a threshold (spec 4.1). math.comb, no scipy.
    """
    succ, total = a_k + b_k, a_n + b_n
    lo, hi = max(0, succ - b_n), min(a_n, succ)
    denom = math.comb(total, a_n)

    def p_of(x):
        return math.comb(succ, x) * math.comb(total - succ, a_n - x) / denom

    observed = p_of(a_k)
    return min(1.0, sum(p_of(x) for x in range(lo, hi + 1)
                        if p_of(x) <= observed * (1 + 1e-9)))


def select(rows, windows):
    out = []
    for since, until in windows:
        out += [r for r in rows if r.get("ts", "") > since
                and (until == "-" or r.get("ts", "") <= until)]
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--window", nargs=2, action="append", required=True,
                    metavar=("FROM", "TO"),
                    help="FROM exclusive, TO inclusive or '-'; repeatable")
    args = ap.parse_args(argv)
    rows = [json.loads(l) for l in (ROOT / "results.jsonl").read_text(encoding="utf-8").splitlines()
            if l.strip()]
    batch = select(rows, args.window)
    v = validity(batch)

    print("rows in window(s): %d | valid: %d | smoke row %s excluded"
          % (len(batch), len(_valid(batch)), SMOKE_TS))
    print("\nSPEC 4.2 -- read first")
    if v["control"] == "incomplete":
        print("  control: INCOMPLETE -- %d of 12 valid sessions (spec 4.3: postponed, not void)"
              % v["control_valid"])
    else:
        print("  control: %s (12 valid)" % v["control"].upper())
    if v["incomplete_cells"]:
        print("  incomplete cells (valid / %d):" % N_PER_CELL)
        for task, arm, n in v["incomplete_cells"]:
            print("    %-34s %s  %d" % (task, arm, n))
    print("  treatment rows missing their skill: %d" % len(v["undelivered"]))

    if v["control"] != "holds" or v["incomplete_cells"] or v["undelivered"]:
        print("\nSPEC 4.1 -- NOT READ. The batch is not complete and clean.")
        return 0

    c = criterion(batch)
    print("\nSPEC 4.1 -- pooled across both tasks")
    print("  C  %d/%d" % (c["C"]["resolved"], c["C"]["n"]))
    for arm, label in (("R", "relevant"), ("I", "irrelevant")):
        a = c[arm]
        print("  %s  %d/%d  %d below control  -> %s  (Fisher p = %.3f, reported, not a threshold)"
              % (arm, a["resolved"], a["n"], a["below_control"], a["verdict"].upper(), a["p"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
