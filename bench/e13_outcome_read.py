#!/usr/bin/env python3
"""Read the E13 outcome test (spec section 8): does the tokenizer fix improve outcomes?

docs/superpowers/specs/2026-09-13-e13-author-traps-design.md

Two arms of 6, told apart by env.plugin_commit: the plugin snapshot at 06885c0
(old tokenizer) and at 9cbb472 (new). Qualification predicted the old hook
leaves trap 2's draft out and the new one delivers it. A row that contradicts
that is void and re-run, and a second one voids its arm. A session refused at
the session limit postpones the whole batch.

Criterion: new minus old resolved >= 3 improves; within 1 is no large effect;
exactly 2 is ambiguous. Fisher's exact p (two-sided) is reported, never used as
a threshold. Run:

    python3 bench/e13_outcome_read.py --trap C --window <OUTCOME_START> -
"""
import argparse
import json
import subprocess
import sys
from math import comb
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from e12_read import select  # noqa: E402
from e13_probe_read import _draft_path  # noqa: E402

N_ARM = 6
LIMIT_MARK = "session limit"
OLD_REF, NEW_REF = "06885c0", "9cbb472"


def fisher_two_sided(a, b, c, d):
    """p for the 2x2 table [[a, b], [c, d]], summing tables no likelier than it."""
    n1, n2, k = a + b, c + d, a + c
    total = comb(n1 + n2, k)
    p = lambda x: comb(n1, x) * comb(n2, k - x) / total
    observed = p(a)
    return min(1.0, sum(p(x) for x in range(max(0, k - n2), min(k, n1) + 1)
                        if p(x) <= observed * (1 + 1e-9)))


def _verdict(diff):
    if diff >= 3:
        return "improves"
    if abs(diff) <= 1:
        return "no large effect"
    if abs(diff) == 2:
        return "ambiguous"
    return "worse (not pre-registered)"


def read_outcome(rows, task, draft_name, draft_path, old_commit, new_commit):
    mine = [r for r in rows if r.get("task") == task and r.get("arm") == "treatment"]
    if any(not r.get("session_ok") and LIMIT_MARK in (r.get("session_tail") or "")
           for r in mine):
        return {"batch": "postponed", "arms": {}, "diff": None, "verdict": None, "p": None,
                "reason": "a session hit the session limit: re-run the whole batch"}
    arms = {}
    for label, commit, want in (("old", old_commit, False), ("new", new_commit, True)):
        trt = [r for r in mine if (r.get("env") or {}).get("plugin_commit") == commit
               and _draft_path(r.get("skill_path")) == draft_path
               and len(r.get("extra_skills") or []) == 7]
        ran = [r for r in trt if r.get("session_ok")]
        match = [r for r in ran
                 if (draft_name in {i.get("skill") for i in r.get("injections") or []}) == want]
        counted = match[:N_ARM]
        a = {"valid": len(counted), "needed": N_ARM,
             "resolved": sum(1 for r in counted if r.get("resolved")),
             "mismatched": len(ran) - len(match), "rerun": len(trt) - len(match)}
        a["status"] = ("void" if a["mismatched"] >= 2 else
                       "complete" if a["valid"] >= N_ARM else "incomplete")
        arms[label] = a
    out = {"arms": arms, "diff": None, "verdict": None, "p": None}
    if any(a["status"] == "void" for a in arms.values()):
        out.update(batch="void", reason="an arm's delivery contradicted qualification twice")
    elif any(a["status"] == "incomplete" for a in arms.values()):
        out.update(batch="incomplete", reason="an arm is not fully measured")
    else:
        o, n = arms["old"]["resolved"], arms["new"]["resolved"]
        out.update(batch="complete", reason="", diff=n - o, verdict=_verdict(n - o),
                   p=fisher_two_sided(n, N_ARM - n, o, N_ARM - o))
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--trap", required=True)
    ap.add_argument("--window", nargs=2, action="append", required=True, metavar=("FROM", "TO"))
    args = ap.parse_args(argv)
    q = json.loads((ROOT / "distilled" / args.trap / "qualification.json").read_text(encoding="utf-8"))
    name = next(r["name"] for r in q["drafts"] if r["path"] == q["first_qualifying"])
    full = lambda ref: "archive:" + subprocess.run(
        ["git", "rev-parse", ref + "^{commit}"], cwd=str(ROOT.parent),
        capture_output=True, text=True, check=True).stdout.strip()
    rows = [json.loads(l) for l in (ROOT / "results.jsonl").read_text(encoding="utf-8").splitlines()
            if l.strip()]
    res = read_outcome(select(rows, args.window), q["task"], name, q["first_qualifying"],
                        full(OLD_REF), full(NEW_REF))
    print("batch: %s%s" % (res["batch"], " -- " + res["reason"] if res["reason"] else ""))
    for label, a in res["arms"].items():
        print("  %-3s valid %d/%d  resolved %d  mismatched %d  re-run %d  %s"
              % (label, a["valid"], a["needed"], a["resolved"], a["mismatched"], a["rerun"], a["status"]))
    if res["verdict"]:
        print("verdict: %s (new - old = %+d, Fisher p = %.3f)" % (res["verdict"], res["diff"], res["p"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
