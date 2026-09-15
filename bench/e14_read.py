#!/usr/bin/env python3
"""Read the E14 batch (spec sections 4-5): trigger x kind on trap C.

docs/superpowers/specs/2026-09-14-e14-trigger-kind-design.md

Four hand-written drafts -- skill/anti-skill x failure-time/write-time
trigger -- each installed alone, 6 runs, plus a same-batch control of 3.

A row refused at the session limit postpones the whole batch. A resolved
control voids it. A row audit.counts() rejects, a failed session, or a draft
row that did not inject its draft does not count and is repeated; a second
undelivered row voids that cell, and a void cell means no effect is computed.
Each cell counts its first 6 valid runs, the control its first 3.

Trigger effect = (SW + AW) - (SF + AF); kind effect = (AF + AW) - (SF + SW).
+4 or more: the factor matters. -1..+1: no large effect. Otherwise ambiguous,
except -4 or less, which is reported but not pre-registered. Fisher's p is
reported, never a threshold. Run:

    python3 bench/e14_read.py --window <E14_START> -
    python3 bench/e14_read.py --window <E14_START> - --todo
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from audit import counts  # noqa: E402
from e12_read import select  # noqa: E402
from e13_outcome_read import fisher_two_sided  # noqa: E402

TASK = "sf-author-verdict-from"
CELLS = ("sf", "sw", "af", "aw")
N_CELL = 6
N_CONTROL = 3
LIMIT_MARK = "session limit"
DRAFT_DIR = "bench/drafts/E14/"


def draft_name(cell):
    return "e14-quote-gate-rewrap-" + cell


def cell_of(row):
    """The E14 cell a treatment row installed, from its skill_path, or None."""
    path = row.get("skill_path") or ""
    return next((c for c in CELLS if path.endswith(DRAFT_DIR + draft_name(c) + ".md")), None)


def band(effect):
    if effect >= 4:
        return "factor matters"
    if effect <= -4:
        return "opposite effect (not pre-registered)"
    if abs(effect) <= 1:
        return "no large effect"
    return "ambiguous"


def _valid(row):
    return counts(row) and bool(row.get("session_ok"))


def _effect(high, low):
    """Effect of (high cells) - (low cells), each side pooled over 12 runs."""
    return {"diff": high - low, "reading": band(high - low),
            "p": fisher_two_sided(high, 2 * N_CELL - high, low, 2 * N_CELL - low)}


def read_batch(rows):
    mine = [r for r in rows if r.get("task") == TASK]
    if any(not r.get("session_ok") and LIMIT_MARK in (r.get("session_tail") or "")
           for r in mine):
        return {"batch": "postponed", "reason": "a session hit the session limit: re-run the whole batch",
                "control": None, "cells": {}, "effects": None, "baseline": None}
    control = [r for r in mine if r.get("arm") == "control"]
    ok = [r for r in control if _valid(r)]
    out = {"control": {"valid": min(len(ok), N_CONTROL), "needed": N_CONTROL,
                       # Every valid control run, not just the first 3: one
                       # resolution anywhere voids the batch (spec section 4).
                       "resolved": sum(1 for r in ok if r.get("resolved")),
                       "invalid": len(control) - len(ok)},
           "cells": {}, "effects": None, "baseline": None}
    if out["control"]["resolved"]:
        out.update(batch="void", reason="the control resolved (spec section 4)")
        return out
    complete = out["control"]["valid"] >= N_CONTROL
    for c in CELLS:
        trt = [r for r in mine if r.get("arm") == "treatment" and cell_of(r) == c]
        valid = [r for r in trt if _valid(r)]
        hit = [r for r in valid
               if draft_name(c) in {i.get("skill") for i in r.get("injections") or []}]
        counted = hit[:N_CELL]
        cell = {"valid": len(counted), "needed": N_CELL,
                "resolved": sum(1 for r in counted if r.get("resolved")),
                "undelivered": len(valid) - len(hit), "invalid": len(trt) - len(valid)}
        cell["status"] = ("void" if cell["undelivered"] >= 2 else
                          "complete" if cell["valid"] >= N_CELL else "incomplete")
        complete = complete and cell["status"] != "incomplete"
        out["cells"][c] = cell
    if not complete:
        out.update(batch="incomplete", reason="the control or a cell is not fully measured")
        return out
    void = [c for c in CELLS if out["cells"][c]["status"] == "void"]
    if void:
        out.update(batch="complete",
                   reason="cell(s) %s void: neither effect is computed" % ", ".join(void))
        return out
    R = {c: out["cells"][c]["resolved"] for c in CELLS}
    out["effects"] = {"trigger": _effect(R["sw"] + R["aw"], R["sf"] + R["af"]),
                      "kind": _effect(R["af"] + R["aw"], R["sf"] + R["sw"])}
    out["baseline"] = {"sf": R["sf"], "af": R["af"],
                       "sf_as_predicted": R["sf"] <= 1, "af_as_predicted": R["af"] >= 5}
    out.update(batch="complete", reason="")
    return out


def todo(res):
    """One entry per run still needed, for bench/e14_probe.sh's repeat loop."""
    if res["batch"] != "incomplete":
        return []
    need = ["control"] * (N_CONTROL - res["control"]["valid"])
    for c in CELLS:
        cell = res["cells"][c]
        if cell["status"] == "incomplete":
            need += [c] * (N_CELL - cell["valid"])
    return need


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--window", nargs=2, action="append", required=True, metavar=("FROM", "TO"))
    ap.add_argument("--todo", action="store_true",
                    help="print only the runs still needed, one per line")
    args = ap.parse_args(argv)
    rows = [json.loads(l) for l in (ROOT / "results.jsonl").read_text(encoding="utf-8").splitlines()
            if l.strip()]
    res = read_batch(select(rows, args.window))
    if args.todo:
        for arm in todo(res):
            print(arm)
        return 0
    print("batch: %s%s" % (res["batch"], " -- " + res["reason"] if res["reason"] else ""))
    if res["control"]:
        c = res["control"]
        print("  control  valid %d/%d  resolved %d  invalid %d"
              % (c["valid"], c["needed"], c["resolved"], c["invalid"]))
    for cell, c in res["cells"].items():
        print("  %-7s  valid %d/%d  resolved %d  undelivered %d  invalid %d  %s"
              % (cell, c["valid"], c["needed"], c["resolved"], c["undelivered"], c["invalid"],
                 c["status"]))
    if res["effects"]:
        for name, e in res["effects"].items():
            print("%s effect: %+d -- %s (Fisher p = %.3f)" % (name, e["diff"], e["reading"], e["p"]))
        b = res["baseline"]
        print("baseline: SF %d/6 (%s), AF %d/6 (%s)"
              % (b["sf"], "as predicted" if b["sf_as_predicted"] else "MOVED",
                 b["af"], "as predicted" if b["af_as_predicted"] else "MOVED"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
