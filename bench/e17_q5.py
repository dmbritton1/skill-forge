#!/usr/bin/env python3
"""E17: does the critique conjunct of the `trusted` gate predict outcome?

docs/superpowers/specs/2026-09-16-e17-critique-gate-prediction-design.md

Brief Q5. The corpus is the nine frozen drafts E15 left behind, which split
cleanly on OUTCOME -- six variant drafts at 18/18 on sf-author-verdict-from,
three E13 baseline drafts at 0/9 -- and which carry no critique verdict,
because the bench suppresses the spawn. Critique them and see whether the
gate's verdict tracks that split.

SPENDS REAL MODEL CALLS -- three `claude -p` turns per draft, 27 in total, on
critique's own shipped default model. Never run this from a test suite;
`tests/` is forbidden from invoking a model, which is why it lives here.

It calls validate.critique() directly, as bench/critique-calibration/run.py
does: no ledger row, no trust entry, nothing installed, the operator's library
untouched. Results append to bench/e17-q5-results.json after every call, so an
interrupted run resumes where it stopped.

    python3 bench/e17_q5.py --dry-run     # guards and plan, 0 calls
    python3 bench/e17_q5.py               # run (resumes)
    python3 bench/e17_q5.py --read        # apply the spec's bands, 0 calls
"""
import argparse
import json
import sys
from fractions import Fraction
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent
sys.path.insert(0, str(ROOT))
from e13_outcome_read import fisher_two_sided  # noqa: E402

RESULTS = ROOT / "e17-q5-results.json"
N_CALLS = 3          # spec section 2: one call is not a measurement
MAX_INCONCLUSIVE = 1  # spec section 2: a second inconclusive drops the draft
MIN_LIVE = 3         # spec section 2: a group below this is not read
UNANIMOUS_MIN = 7    # spec section 3.2: fewer than this and the gate is unstable

# Spec section 1. The grouping is E15's own, and the paths are frozen.
CORPUS = (
    [("V", "distilled/C/learn-e15-nogate/%d/SKILL.md" % i) for i in range(1, 7)] +
    [("B", "distilled/C/learn-nogate/%d/SKILL.md" % i) for i in range(1, 4)])


def band(delta, pv):
    """Spec section 3.1. Same shape as E15's, deliberately."""
    if delta >= Fraction(2, 5) and pv >= Fraction(1, 2):
        return "the gate predicts"
    if abs(delta) <= Fraction(3, 20):
        return "the gate does not predict"
    if delta <= -Fraction(2, 5):
        return "the gate predicts backwards"
    return "ambiguous"


def read_results(records):
    """Apply the spec's two co-primary measures to {path: {group, bytes, calls}}.

    A call is "pass", "fail" or "inconclusive". A draft with more than
    MAX_INCONCLUSIVE inconclusive calls is dropped and its group's n falls.
    Pv and Pb pool the NON-inconclusive calls of live drafts, which is 18 and 9
    when nothing was inconclusive.
    """
    drafts, tally = {}, {"V": [0, 0], "B": [0, 0]}
    unanimous = 0
    for path, rec in records.items():
        calls = rec["calls"]
        bad = sum(1 for c in calls if c == "inconclusive")
        live = bad <= MAX_INCONCLUSIVE and len(calls) >= N_CALLS
        graded = [c for c in calls if c != "inconclusive"]
        passes = sum(1 for c in graded if c == "pass")
        majority = ("inconclusive" if not graded else
                    "pass" if passes * 2 > len(graded) else "fail")
        # A dropped draft is never unanimous, which can only push the reading
        # toward `unstable` -- the conservative direction.
        agree = live and len(set(calls)) == 1
        unanimous += bool(agree)
        drafts[path] = {"group": rec["group"], "bytes": rec.get("bytes"),
                        "calls": list(calls), "live": live, "passes": passes,
                        "graded": len(graded), "majority": majority,
                        "unanimous": bool(agree)}
        if live:
            tally[rec["group"]][0] += passes
            tally[rec["group"]][1] += len(graded)
    complete = len(records) >= len(CORPUS)
    out = {"drafts": drafts, "unanimous": unanimous, "of": len(records),
           # Stability is a verdict about the whole corpus, so a partial run
           # has not measured it -- calling that "unstable" would read an
           # unfinished batch as a finding.
           "stability": ("not measured" if not complete else
                         "unstable" if unanimous < UNANIMOUS_MIN else "stable"),
           "measures": None, "reason": ""}
    live_n = {g: sum(1 for d in drafts.values() if d["live"] and d["group"] == g)
              for g in ("V", "B")}
    out["live"] = live_n
    if not complete:
        out["reason"] = "not every draft has been critiqued yet"
        return out
    if min(live_n.values()) < MIN_LIVE:
        out["reason"] = "a group has fewer than %d live drafts" % MIN_LIVE
        return out
    (vp, vn), (bp, bn) = tally["V"], tally["B"]
    if not vn or not bn:
        out["reason"] = "a group has no graded call"
        return out
    delta = Fraction(vp, vn) - Fraction(bp, bn)
    out["measures"] = {"V": [vp, vn], "B": [bp, bn], "delta": round(float(delta), 2),
                       "reading": band(delta, Fraction(vp, vn)),
                       "p": fisher_two_sided(vp, vn - vp, bp, bn - bp)}
    return out


def load():
    if RESULTS.exists():
        return json.loads(RESULTS.read_text(encoding="utf-8"))
    return {}


def save(records):
    RESULTS.write_text(json.dumps(records, indent=2) + "\n", encoding="utf-8")


def report(res):
    print("stability: %s -- %d of %d drafts unanimous over %d calls (needs %d)"
          % (res["stability"], res["unanimous"], res["of"], N_CALLS, UNANIMOUS_MIN))
    for path, d in res["drafts"].items():
        print("  %-3s %-40s %-24s %s%s"
              % (d["group"], path.replace("distilled/C/", "").replace("/SKILL.md", ""),
                 " ".join(d["calls"]), d["majority"],
                 "" if d["live"] else "  DROPPED"))
    m = res["measures"]
    if not m:
        print("not readable: %s" % (res["reason"] or "incomplete"))
        return
    print("V %d/%d  B %d/%d  delta = %+.2f -- %s (Fisher p = %.3f)"
          % (m["V"][0], m["V"][1], m["B"][0], m["B"][1], m["delta"],
             m["reading"], m["p"]))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true", help="guards and plan, no model call")
    ap.add_argument("--read", action="store_true", help="read the results file, no model call")
    args = ap.parse_args(argv)

    missing = [p for _, p in CORPUS if not (ROOT / p).is_file()]
    if missing:
        print("FATAL: corpus draft missing: %s" % missing, file=sys.stderr)
        return 1
    records = load()
    if args.read:
        report(read_results(records))
        return 0
    if args.dry_run:
        todo = sum(max(0, N_CALLS - len(records.get(p, {}).get("calls", [])))
                   for _, p in CORPUS)
        print("corpus ok: %d drafts, %d calls each; %d call(s) still to make"
              % (len(CORPUS), N_CALLS, todo))
        return 0

    import validate  # noqa: E402  -- imported late: --dry-run and --read need no model path
    for group, rel in CORPUS:
        path = ROOT / rel
        rec = records.setdefault(rel, {"group": group, "bytes": len(
            path.read_text(encoding="utf-8")), "calls": []})
        text = path.read_text(encoding="utf-8")
        # An inconclusive call is re-run once (spec section 2), so a slot may
        # cost two turns; the second inconclusive is recorded and drops the draft.
        while len(rec["calls"]) < N_CALLS:
            verdict, _ = validate.critique(text, {"kind": "skill"}, str(REPO))
            if verdict == "inconclusive":
                verdict, _ = validate.critique(text, {"kind": "skill"}, str(REPO))
            rec["calls"].append(verdict)
            save(records)
            print("%-3s %-44s %s" % (group, rel.replace("distilled/C/", ""), verdict))
    report(read_results(records))
    return 0


if __name__ == "__main__":
    sys.exit(main())
