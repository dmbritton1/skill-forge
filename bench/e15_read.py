#!/usr/bin/env python3
"""Read the E15 probe batch (spec sections 3-5).

docs/superpowers/specs/2026-09-14-e15-distiller-rules-design.md

Variant drafts (distilled under bench/variants/E15/distilling-skills.md) and
E13's three skill drafts (the baseline), each installed alone, 3 runs each,
plus a same-batch control of 3, in three interleaved rounds.

A row refused at the session limit postpones the batch. A valid control that
resolves voids it. A row audit.counts() rejects, a failed session, or a draft
row that did not inject its draft does not count; a second undelivered row
voids that draft. A void variant draft drops out of V; a void baseline draft
means d is not computed. Each draft counts its first 3 valid runs.

V and B are pooled resolved/valid; d = V - B. d >= +0.40 with V >= 0.50: the
rules help. |d| <= 0.15: no large effect. d <= -0.40: the rules hurt.
Otherwise ambiguous. Fisher's p is reported, never a threshold. Run:

    python3 bench/e15_read.py --order
    python3 bench/e15_read.py --window <E15_START> -
    python3 bench/e15_read.py --window <E15_START> - --todo
"""
import argparse
import json
import sys
from fractions import Fraction
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from audit import counts  # noqa: E402
from e12_read import select  # noqa: E402
from e13_outcome_read import fisher_two_sided  # noqa: E402

TASK = "sf-author-verdict-from"
N_DRAFT = 3
N_CONTROL = 3
ROUNDS = 3
LIMIT_MARK = "session limit"
RECORD = ROOT / "distilled" / "C" / "e15-probe.json"


def probe_drafts(record):
    """The drafts the probe runs: delivered variant drafts in record order, then the baseline."""
    rows = [r for r in record["drafts"] if r["delivered"]]
    pick = lambda group: [{"group": group, "path": r["path"], "name": r["name"]}
                          for r in rows if r["group"] == group]
    return pick("variant") + pick("baseline")


def order(drafts):
    """Spec section 3: v1, b1, v2, b2, v3, b3, remaining variants; rotated left
    by the round number; each round opens with a control run."""
    v = [d["path"] for d in drafts if d["group"] == "variant"]
    b = [d["path"] for d in drafts if d["group"] == "baseline"]
    mixed = []
    for i in range(max(len(v), len(b))):
        mixed += v[i:i + 1] + b[i:i + 1]
    out = []
    for r in range(ROUNDS):
        k = r % len(mixed)
        out += ["control"] + mixed[k:] + mixed[:k]
    return out


def draft_of(row, drafts):
    path = row.get("skill_path") or ""
    return next((d for d in drafts if path.endswith(d["path"])), None)


def band(d, v):
    if d >= Fraction(2, 5) and v >= Fraction(1, 2):
        return "the rules help"
    if abs(d) <= Fraction(3, 20):
        return "no large effect"
    if d <= -Fraction(2, 5):
        return "the rules hurt"
    return "ambiguous"


def _valid(row):
    return counts(row) and bool(row.get("session_ok"))


def read_batch(rows, drafts):
    mine = [r for r in rows if r.get("task") == TASK]
    if any(not r.get("session_ok") and LIMIT_MARK in (r.get("session_tail") or "")
           for r in mine):
        return {"batch": "postponed", "reason": "a session hit the session limit: re-run the whole batch",
                "control": None, "drafts": {}, "measures": None}
    control = [r for r in mine if r.get("arm") == "control"]
    ok = [r for r in control if _valid(r)]
    out = {"control": {"valid": min(len(ok), N_CONTROL), "needed": N_CONTROL,
                       # Every VALID control run: one valid resolution voids the
                       # batch. An invalid row never counts, so its resolution does not.
                       "resolved": sum(1 for r in ok if r.get("resolved")),
                       "invalid": len(control) - len(ok)},
           "drafts": {}, "measures": None}
    if out["control"]["resolved"]:
        out.update(batch="void", reason="the control resolved (spec section 3)")
        return out
    complete = out["control"]["valid"] >= N_CONTROL
    for d in drafts:
        trt = [r for r in mine if r.get("arm") == "treatment" and draft_of(r, drafts) is d]
        valid = [r for r in trt if _valid(r)]
        hit = [r for r in valid if d["name"] in {i.get("skill") for i in r.get("injections") or []}]
        counted = hit[:N_DRAFT]
        cell = {"group": d["group"], "valid": len(counted), "needed": N_DRAFT,
                "resolved": sum(1 for r in counted if r.get("resolved")),
                "undelivered": len(valid) - len(hit), "invalid": len(trt) - len(valid)}
        cell["status"] = ("void" if cell["undelivered"] >= 2 else
                          "complete" if cell["valid"] >= N_DRAFT else "incomplete")
        complete = complete and cell["status"] != "incomplete"
        out["drafts"][d["path"]] = cell
    if not complete:
        out.update(batch="incomplete", reason="the control or a draft is not fully measured")
        return out
    cells = list(out["drafts"].values())
    if any(c["group"] == "baseline" and c["status"] == "void" for c in cells):
        out.update(batch="complete", reason="a baseline draft is void: d is not computed")
        return out
    live = [c for c in cells if c["group"] == "variant" and c["status"] != "void"]
    if not live:
        out.update(batch="complete", reason="every variant draft is void: d is not computed")
        return out
    vr, vv = sum(c["resolved"] for c in live), sum(c["valid"] for c in live)
    base = [c for c in cells if c["group"] == "baseline"]
    br, bv = sum(c["resolved"] for c in base), sum(c["valid"] for c in base)
    d = Fraction(vr, vv) - Fraction(br, bv)
    out["measures"] = {"V": [vr, vv], "B": [br, bv], "d": round(float(d), 2),
                       "reading": band(d, Fraction(vr, vv)),
                       "p": fisher_two_sided(vr, vv - vr, br, bv - br),
                       "baseline_moved": br >= 5}
    out.update(batch="complete", reason="")
    return out


def todo(res, drafts):
    """One entry per run still needed, for bench/e15_probe.sh's repeat loop."""
    if res["batch"] != "incomplete":
        return []
    need = ["control"] * (N_CONTROL - res["control"]["valid"])
    for d in drafts:
        cell = res["drafts"][d["path"]]
        if cell["status"] == "incomplete":
            need += [d["path"]] * (N_DRAFT - cell["valid"])
    return need


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--window", nargs=2, action="append", metavar=("FROM", "TO"))
    ap.add_argument("--todo", action="store_true", help="print only the runs still needed")
    ap.add_argument("--order", action="store_true", help="print the pre-registered run order")
    ap.add_argument("--record", default=str(RECORD), help="e15-probe.json (tests pass a copy)")
    args = ap.parse_args(argv)
    drafts = probe_drafts(json.loads(Path(args.record).read_text(encoding="utf-8")))
    if args.order:
        for arm in order(drafts):
            print(arm)
        return 0
    if not args.window:
        ap.error("--window is required unless --order")
    rows = [json.loads(l) for l in (ROOT / "results.jsonl").read_text(encoding="utf-8").splitlines()
            if l.strip()]
    res = read_batch(select(rows, args.window), drafts)
    if args.todo:
        for arm in todo(res, drafts):
            print(arm)
        return 0
    print("batch: %s%s" % (res["batch"], " -- " + res["reason"] if res["reason"] else ""))
    if res["control"]:
        c = res["control"]
        print("  control  valid %d/%d  resolved %d  invalid %d"
              % (c["valid"], c["needed"], c["resolved"], c["invalid"]))
    for path, c in res["drafts"].items():
        print("  %-8s %-34s valid %d/%d  resolved %d  undelivered %d  invalid %d  %s"
              % (c["group"], path.replace("bench/distilled/C/", ""), c["valid"], c["needed"],
                 c["resolved"], c["undelivered"], c["invalid"], c["status"]))
    m = res["measures"]
    if m:
        print("V %d/%d  B %d/%d  d = %+.2f -- %s (Fisher p = %.3f)"
              % (m["V"][0], m["V"][1], m["B"][0], m["B"][1], m["d"], m["reading"], m["p"]))
        if m["baseline_moved"]:
            print("baseline: B %d/%d -- MOVED (E13 measured 1/9)" % (m["B"][0], m["B"][1]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
