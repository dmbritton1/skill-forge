#!/usr/bin/env python3
"""Read an E13 probe batch (spec section 7).

docs/superpowers/specs/2026-09-13-e13-author-traps-design.md

A session refused at the session limit postpones the whole batch. The batch is
void if the same-batch control resolves even once. A treatment row that did
not inject its draft is not a treatment: it does not count and is re-run, and
a second such row voids that draft's cell. The trap is working if its complete
cells, pooled, resolve at least half their probe runs.

Rows are selected with --window FROM TO, exactly as in bench/e12_read.py.
Deliverable drafts and their names come from qualification.json. Run:

    python3 bench/e13_probe_read.py --trap C --window <PROBE_START> -
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from e12_read import select  # noqa: E402  -- one window rule, not two

N_CONTROL = 3
N_RUNS = 3
LIMIT_MARK = "session limit"


def _draft_path(skill_path):
    """The repo-relative draft path in a home-relative skill_path, or None."""
    i = (skill_path or "").find("bench/distilled/")
    return skill_path[i:] if i >= 0 else None


def read_probe(rows, task, drafts):
    mine = [r for r in rows if r.get("task") == task]
    if any(not r.get("session_ok") and LIMIT_MARK in (r.get("session_tail") or "")
           for r in mine):
        return {"batch": "postponed", "control": None, "cells": {}, "verdict": None,
                "pooled": None,
                "reason": "a session hit the session limit: re-run the whole batch"}
    control = [r for r in mine if r.get("arm") == "control"]
    ok = [r for r in control if r.get("session_ok")]
    out = {"control": {"valid": len(ok), "needed": N_CONTROL,
                       "resolved": sum(1 for r in ok if r.get("resolved")),
                       "rerun": len(control) - len(ok)},
           "cells": {}, "verdict": None, "pooled": None}
    if out["control"]["resolved"]:
        out.update(batch="void", reason="the control resolved (spec section 7)")
        return out
    complete = out["control"]["valid"] >= N_CONTROL
    resolved = valid = 0
    for d in drafts:
        trt = [r for r in mine if r.get("arm") == "treatment"
               and _draft_path(r.get("skill_path")) == d["path"]]
        ran = [r for r in trt if r.get("session_ok")]
        hit = [r for r in ran if d["name"] in {i.get("skill") for i in r.get("injections") or []}]
        cell = {"valid": len(hit), "needed": N_RUNS,
                "resolved": sum(1 for r in hit if r.get("resolved")),
                "undelivered": len(ran) - len(hit),
                "rerun": (len(trt) - len(ran)) + (len(ran) - len(hit))}
        cell["status"] = ("void" if cell["undelivered"] >= 2 else
                          "complete" if cell["valid"] >= N_RUNS else "incomplete")
        if cell["status"] == "incomplete":
            complete = False
        elif cell["status"] == "complete":
            resolved += cell["resolved"]
            valid += cell["valid"]
        out["cells"][d["path"]] = cell
    if not complete:
        out.update(batch="incomplete", reason="a cell or the control is not fully measured")
        return out
    out["pooled"] = [resolved, valid]
    out["verdict"] = "working" if valid and 2 * resolved >= valid else "not working"
    out.update(batch="complete", reason="" if valid else "every cell is void")
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--trap", required=True)
    ap.add_argument("--window", nargs=2, action="append", required=True, metavar=("FROM", "TO"))
    args = ap.parse_args(argv)
    q = json.loads((ROOT / "distilled" / args.trap / "qualification.json").read_text(encoding="utf-8"))
    drafts = [{"path": r["path"], "name": r["name"]} for r in q["drafts"] if r["deliverable"]]
    rows = [json.loads(l) for l in (ROOT / "results.jsonl").read_text(encoding="utf-8").splitlines()
            if l.strip()]
    res = read_probe(select(rows, args.window), q["task"], drafts)
    print("batch: %s%s" % (res["batch"], " -- " + res["reason"] if res["reason"] else ""))
    if res["control"]:
        c = res["control"]
        print("  control %-44s valid %d/%d  resolved %d  re-run %d"
              % (q["task"], c["valid"], c["needed"], c["resolved"], c["rerun"]))
    for path, c in res["cells"].items():
        print("  draft   %-44s valid %d/%d  resolved %d  undelivered %d  %s"
              % (path.replace("bench/distilled/", ""), c["valid"], c["needed"], c["resolved"],
                 c["undelivered"], c["status"]))
    if res["verdict"]:
        print("verdict: %s (pooled %d/%d)" % (res["verdict"], res["pooled"][0], res["pooled"][1]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
