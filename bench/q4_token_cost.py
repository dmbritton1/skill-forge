#!/usr/bin/env python3
"""Brief Q4: what does a unit of benefit cost in injected tokens?

`bench/RESULTS.md` records Q4 as "No experiment exists". One does not need a
session: every input is already on disk. Injection cost is a fixed formula in
the shipped selector, every injected skill file resolves in this repo, and the
resolved rates are in results.jsonl.

THE METRIC. For one task and one injected skill:

    cost   = retrieve.injection_cost(whole file)   -- what the selector charges
    lift   = treatment resolved rate - the task's control rate
    price  = cost / lift    -- tokens spent per ADDITIONAL resolved run

`price` is the answer to Q4 as the brief phrases it. A skill that never
resolves has no price, only a bill: its cost times the runs that paid it.

SCOPE, and why it is this narrow. Lift needs a control that can rise, so this
reads only tasks whose control floor is measured at ZERO. That is derived, not
hardcoded, and it selects exactly the two working author traps. Excluded, with
the reason printed:

  - repair-mode tasks, whose control already sits at ceiling (no room to lift);
  - `sf-author-response-text`, retired by E10 with a control of 7/19;
  - any run where more than one skill injected, because the cost cannot be
    attributed to one of them. That drops the dilution arms (E6, E10, E12),
    which are harm measurements and not benefit measurements anyway.

Rows are filtered exactly as every other reader filters them: `audit.counts`
plus `session_ok`. Lifetime rows, pooled across batches -- this is a cost
ratio, not a contrast between arms, so it does not need one batch's window.

Deterministic, 0 sessions, no model. Run: python3 bench/q4_token_cost.py
"""
import argparse
import json
import re
import sys
from fractions import Fraction
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(REPO / "scripts"))
from audit import counts  # noqa: E402
from retrieve import INJECT_BUDGET_TOKENS, injection_cost  # noqa: E402

MIN_CONTROL_N = 6  # a floor read off fewer runs is not a floor


def _valid(row):
    return counts(row) and bool(row.get("session_ok"))


def skill_file(row):
    """The injected draft's path inside this repo, or None."""
    p = row.get("skill_path") or ""
    i = p.find("bench/")
    if i < 0:
        return None
    rel = p[i:]
    return rel if (REPO / rel).is_file() else None


def skill_name(text):
    m = re.search(r"^name:\s*(\S+)", text, re.M)
    return m.group(1) if m else None


def controls(rows):
    """{task: (resolved, n)} over every valid control row, lifetime."""
    out = {}
    for r in rows:
        if r.get("arm") != "control" or not _valid(r):
            continue
        res, n = out.get(r["task"], (0, 0))
        out[r["task"]] = (res + bool(r.get("resolved")), n + 1)
    return out


def cells(rows, ctl):
    """One entry per (task, injected skill file) on a task with a zero floor."""
    out = {}
    for r in rows:
        task = r.get("task")
        base = ctl.get(task)
        if not base or base[0] != 0 or base[1] < MIN_CONTROL_N:
            continue
        if r.get("arm") == "control" or not _valid(r):
            continue
        inj = r.get("injections") or []
        rel = skill_file(r)
        if len(inj) != 1 or rel is None:
            continue   # unattributable cost, or a draft this repo does not hold
        text = (REPO / rel).read_text(encoding="utf-8")
        if inj[0].get("skill") != skill_name(text):
            continue   # the row injected something other than the file it names
        cell = out.setdefault((task, rel), {"resolved": 0, "n": 0,
                                            "cost": injection_cost(text)})
        cell["resolved"] += bool(r.get("resolved"))
        cell["n"] += 1
    return out


def price(cell, control_rate):
    """Tokens per additional resolved run, or None when nothing was gained."""
    lift = Fraction(cell["resolved"], cell["n"]) - control_rate
    if lift <= 0:
        return None
    return int(cell["cost"] / lift)


def report(rows):
    ctl = controls(rows)
    grid = cells(rows, ctl)
    eligible = sorted({t for t, _ in grid})
    print("Q4: tokens per additional resolved run")
    print("injection cost = retrieve.injection_cost (whole file); budget = %d/path\n"
          % INJECT_BUDGET_TOKENS)
    for task in eligible:
        res, n = ctl[task]
        print("%s  -- control %d/%d" % (task, res, n))
        rate0 = Fraction(res, n)
        paid = gained = 0
        for (t, rel), c in sorted(grid.items()):
            if t != task:
                continue
            p = price(c, rate0)
            paid += c["cost"] * c["n"]
            gained += c["resolved"]
            print("  %-42s %4d tok (%3d%% of budget)  %d/%d  %s"
                  % (rel.replace("bench/distilled/", "").replace("bench/", "")
                     .replace("/SKILL.md", ""),
                     c["cost"], round(100 * c["cost"] / INJECT_BUDGET_TOKENS),
                     c["resolved"], c["n"],
                     ("%d tok/resolution" % p) if p else "no lift -- bill only"))
        print("  task total: %d tokens paid, %d extra resolutions, %s\n"
              % (paid, gained,
                 ("%d tok each" % (paid // gained)) if gained else "nothing gained"))
    skipped = sorted(set(ctl) - set(eligible))
    if skipped:
        print("not read (control cannot rise, or n < %d):" % MIN_CONTROL_N)
        for task in skipped:
            res, n = ctl[task]
            print("  %-42s control %d/%d" % (task, res, n))
    return grid


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--json", action="store_true", help="machine-readable cells")
    args = ap.parse_args(argv)
    rows = [json.loads(l) for l in
            (ROOT / "results.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    grid = report(rows)
    if args.json:
        print(json.dumps({"%s|%s" % k: v for k, v in sorted(grid.items())}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
