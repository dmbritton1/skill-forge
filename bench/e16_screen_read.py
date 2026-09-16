#!/usr/bin/env python3
"""Read E16's control screen: the reference first, then each candidate.

docs/superpowers/specs/2026-09-16-e16-author-traps-design.md, section 3.

Written before any screen row existed. The reference is read before any
candidate, and while it is void, mixed or incomplete no candidate is read at
all. E13's screen postponed a whole batch at the session limit; E16 follows
E15 amendment 4 instead -- a failed session never counts, does not take its
slot, and is re-run in its place, so the batch PAUSES and RESUMES across
windows. Batches are still never stitched: every row must carry one CLI
version, model and plugin commit, or the batch is `mixed` and unreadable.

Admission needs more than a zero floor (spec section 3.3). Candidate F grades
64 tests, so a session that never implemented the contract at all would also
read 0/6 -- a floor that says nothing about the trap. Every unresolved control
row is attributed from its `per_test`: `trap` when the ONLY graded test it
fails is the historical bug's own, `wider` otherwise.

Rows are selected with --window FROM TO, exactly as in bench/e12_read.py
(FROM exclusive, TO inclusive, "-" for open), and the flag is repeatable.

Deterministic, 0 sessions. Run:

    python3 bench/e16_screen_read.py --order
    python3 bench/e16_screen_read.py --window <SCREEN_START> -
    python3 bench/e16_screen_read.py --window <SCREEN_START> - --next
    python3 bench/e16_screen_read.py --window <SCREEN_START> - --env
"""
import argparse
import collections
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from audit import counts  # noqa: E402
from e12_read import select  # noqa: E402

REFERENCE = "sf-author-fingerprint-preexisting"
# The historical bug's own test: the one graded test the parent's original
# function fails (bench/e16_preflight.py, run 2). Candidate order is fixed here.
TRAP_TEST = {
    "sf-author-read-markers": "test_read_markers_skips_junk_without_losing_good_lines",
    "sf-author-event-totals": "test_event_totals_sums_null_and_empty_outcome_into_unknown",
}
CANDIDATES = tuple(TRAP_TEST)
N_CANDIDATE = 6
N_REFERENCE = 3
ROUNDS = 3
REPEATS = 6
LIMIT_MARK = re.compile(r"hit your [\w ]*limit")  # session, weekly, Opus ...


def order(expected=CANDIDATES):
    """Three interleaved rounds, each opening with the reference (spec section 3.2).

    E13 ran each cell as one block. Under pause-and-resume a window boundary
    would then fall inside a single cell and confound it with the environment;
    interleaving spreads every cell across the batch's windows instead.
    """
    out = []
    for _ in range(ROUNDS):
        out.append(REFERENCE)
        out += list(expected) * (N_CANDIDATE // ROUNDS)
    return out


def env_of(row):
    env = row.get("env") or {}
    return (env.get("cli"), row.get("model"), env.get("plugin_commit"))


def _valid(row):
    return counts(row) and bool(row.get("session_ok"))


def attribute(row, trap_test):
    """`trap` when the only graded test this row failed is the historical bug's."""
    per = row.get("per_test") or {}
    failed = {n for n, ok in per.items() if not ok}
    return "trap" if failed == {trap_test} else "wider"


def _cell(rows, task, needed):
    mine = [r for r in rows if r.get("task") == task]
    valid = [r for r in mine if _valid(r)]
    counted = valid[:needed]
    return {"valid": len(counted), "needed": needed,
            "resolved": sum(1 for r in counted if r.get("resolved")),
            "invalid": len(mine) - len(valid), "rows": counted}


def read_screen(rows, expected=CANDIDATES):
    """expected: the candidate ids present in bench/tasks.json, in CANDIDATES order."""
    control = [r for r in rows if r.get("arm") == "control"]
    out = {"cells": {}, "reason": ""}
    if len({env_of(r) for r in control}) > 1:
        out.update(screen="mixed",
                   reason="rows from more than one CLI version, model or plugin commit")
        return out
    ref = _cell(control, REFERENCE, N_REFERENCE)
    out["cells"][REFERENCE] = ref
    if ref["resolved"]:
        out.update(screen="void",
                   reason="the reference resolved, so the environment moved (spec section 3.4)")
        return out
    for task in expected:
        cell = _cell(control, task, N_CANDIDATE)
        unresolved = [r for r in cell["rows"] if not r.get("resolved")]
        cell["trap"] = sum(1 for r in unresolved if attribute(r, TRAP_TEST[task]) == "trap")
        cell["wider"] = len(unresolved) - cell["trap"]
        out["cells"][task] = cell
    complete = (ref["valid"] >= N_REFERENCE
                and all(out["cells"][t]["valid"] >= N_CANDIDATE for t in expected))
    if not complete:
        last = control[-1] if control else None
        if last is not None and not last.get("session_ok"):
            limit = bool(LIMIT_MARK.search(last.get("session_tail") or ""))
            out.update(screen="paused", reason="session limit" if limit else "failed session")
        else:
            out.update(screen="incomplete",
                       reason="the reference or a candidate is not fully measured")
        return out
    for task in expected:
        cell = out["cells"][task]
        # Spec section 3.3, pre-registered: a zero floor is necessary, and the
        # trap must also be what produced it in a majority of the cell.
        cell["verdict"] = ("rejected" if cell["resolved"] else
                           "admitted" if cell["trap"] > N_CANDIDATE // 2 else
                           "floor not attributable")
    out.update(screen="complete")
    return out


def todo(res, expected=CANDIDATES):
    if res["screen"] not in ("incomplete", "paused"):
        return []
    need = [REFERENCE] * (N_REFERENCE - res["cells"][REFERENCE]["valid"])
    for task in expected:
        cell = res["cells"].get(task)
        if cell:
            need += [task] * (N_CANDIDATE - cell["valid"])
    return need


def next_run(rows, res, expected=CANDIDATES):
    """Spec section 3.2 (E15 amendment 4): a FINISHED session takes its slot in
    the order; a failed one does not, so it is re-run in place. After the order,
    at most REPEATS finished sessions beyond it, from todo()."""
    if res["screen"] not in ("incomplete", "paused"):
        return None
    done = collections.Counter(r.get("task") for r in rows
                              if r.get("arm") == "control" and r.get("session_ok"))
    plan, seen = order(expected), collections.Counter()
    for task in plan:
        seen[task] += 1
        if seen[task] > done[task]:
            return task
    used = sum(max(0, n - plan.count(t)) for t, n in done.items())
    need = todo(res, expected)
    return need[0] if need and used < REPEATS else None


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--window", nargs=2, action="append", metavar=("FROM", "TO"))
    ap.add_argument("--order", action="store_true", help="print the pre-registered run order")
    ap.add_argument("--next", action="store_true", help="print the next run, or nothing")
    ap.add_argument("--todo", action="store_true", help="print only the runs still needed")
    ap.add_argument("--env", action="store_true", help="print the batch's CLI|model|plugin commit")
    args = ap.parse_args(argv)
    ids = {t["id"] for t in
           json.loads((ROOT / "tasks.json").read_text(encoding="utf-8"))["tasks"]}
    expected = tuple(t for t in CANDIDATES if t in ids)
    if args.order:
        for task in order(expected):
            print(task)
        return 0
    if not args.window:
        ap.error("--window is required unless --order")
    rows = select([json.loads(l) for l in
                   (ROOT / "results.jsonl").read_text(encoding="utf-8").splitlines()
                   if l.strip()], args.window)
    res = read_screen(rows, expected)
    if args.next:
        print(next_run(rows, res, expected) or "")
        return 0
    if args.env:
        for e in {env_of(r) for r in rows if r.get("arm") == "control"}:
            print("|".join(str(x) for x in e))
        return 0
    if args.todo:
        for task in todo(res, expected):
            print(task)
        return 0
    print("screen: %s%s" % (res["screen"], " -- " + res["reason"] if res["reason"] else ""))
    for task, c in res["cells"].items():
        role = "reference" if task == REFERENCE else "candidate"
        extra = ("" if task == REFERENCE else
                 "  unresolved: trap %d, wider %d" % (c["trap"], c["wider"]))
        print("  %-9s %-34s valid %d/%d  resolved %d  invalid %d  %s%s"
              % (role, task, c["valid"], c["needed"], c["resolved"], c["invalid"],
                 c.get("verdict", ""), extra))
    return 0


if __name__ == "__main__":
    sys.exit(main())
