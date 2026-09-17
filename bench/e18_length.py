#!/usr/bin/env python3
"""E18: is critique's negative direction about length, or about outcome?

docs/superpowers/specs/2026-09-16-e18-critique-length-probe-design.md

E17's threat 4 fired completely: its three baseline drafts were the three
shortest files and its six variant drafts the six longest, so "prefers drafts
that do not work" and "prefers shorter drafts" predicted the same thing. The
missing cell is SHORT AND WORKING, and E14's hand-written drafts are it.

A PROBE, not a test: 6 calls over 2 skill drafts for the primary reading. The
spec's section 3 says what that cannot settle, and no p-value is computed.

The two anti-skill drafts are run too and reported SEPARATELY -- `rubric_for`
answers them with ANTISKILL_CRITERIA, which no E17 draft ever exercised, so
they are new ground rather than more of the same and are never pooled.

Method, containment and the inconclusive rule are E17's, imported rather than
copied: validate.critique() called directly, no ledger row, no trust entry,
nothing installed, SKILLFORGE_VALIDATE_MODEL left unset.

SPENDS REAL MODEL CALLS -- 12. Never run from a test suite.

    python3 bench/e18_length.py --dry-run
    python3 bench/e18_length.py
    python3 bench/e18_length.py --read
"""
import argparse
import json
import sys
from fractions import Fraction
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(REPO / "scripts"))
import e17_q5 as q5  # noqa: E402  -- one critique-probe method, not two

RESULTS = ROOT / "e18-length-results.json"
N_CALLS = q5.N_CALLS
# Spec section 1. `group` is the RUBRIC the draft is judged by, because that is
# what makes the two halves unpoolable.
CORPUS = (
    [("skill", "drafts/E14/e14-quote-gate-rewrap-%s.md" % s) for s in ("sf", "sw")] +
    [("antiskill", "drafts/E14/e14-quote-gate-rewrap-%s.md" % s) for s in ("af", "aw")])
# E17's measured anchors, for the report only.
ANCHORS = {"E17 B (short, does not work)": Fraction(6, 9),
           "E17 V (long, works)": Fraction(4, 18)}


def band(pe):
    """Spec section 2, over the SKILL drafts only."""
    if pe >= Fraction(1, 2):
        return "length -- short-and-working patterns with short-and-broken"
    if pe <= Fraction(1, 4):
        return "outcome -- short-and-working patterns with long-and-working"
    return "neither cleanly -- still confounded (spec section 3)"


def read_results(records):
    out = {"drafts": {}, "primary": None, "secondary": None}
    for group in ("skill", "antiskill"):
        rows = {k: v for k, v in records.items() if v["group"] == group}
        graded = [c for v in rows.values() for c in v["calls"] if c != "inconclusive"]
        passes = sum(1 for c in graded if c == "pass")
        cell = {"passes": passes, "graded": len(graded), "drafts": len(rows),
                "unanimous": sum(1 for v in rows.values()
                                 if len(v["calls"]) >= N_CALLS and len(set(v["calls"])) == 1)}
        out["primary" if group == "skill" else "secondary"] = cell
    for k, v in records.items():
        out["drafts"][k] = dict(v)
    p = out["primary"]
    complete = len(records) >= len(CORPUS) and all(
        len(v["calls"]) >= N_CALLS for v in records.values())
    if complete and p["graded"]:
        pe = Fraction(p["passes"], p["graded"])
        out["reading"] = band(pe)
        out["pe"] = round(float(pe), 2)
    else:
        out["reading"] = "incomplete"
    return out


def report(res):
    for k, v in res["drafts"].items():
        print("  %-10s %-38s %s" % (v["group"], k.replace("drafts/E14/", ""),
                                    " ".join(v["calls"])))
    for label, key in (("primary  (skill rubric)", "primary"),
                       ("secondary (antiskill)", "secondary")):
        c = res[key]
        print("%s: %d/%d passes over %d drafts, %d unanimous"
              % (label, c["passes"], c["graded"], c["drafts"], c["unanimous"]))
    if res["reading"] == "incomplete":
        print("not readable: not every draft has been critiqued yet")
        return
    print("\nPe = %.2f -- %s" % (res["pe"], res["reading"]))
    for label, v in ANCHORS.items():
        print("  anchor %-32s %.2f" % (label, float(v)))
    print("no p-value: spec section 3 -- 6 calls cannot settle this, only point")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--read", action="store_true")
    args = ap.parse_args(argv)
    missing = [p for _, p in CORPUS if not (ROOT / p).is_file()]
    if missing:
        print("FATAL: corpus draft missing: %s" % missing, file=sys.stderr)
        return 1
    records = json.loads(RESULTS.read_text(encoding="utf-8")) if RESULTS.exists() else {}
    if args.read:
        report(read_results(records))
        return 0
    if args.dry_run:
        import validate  # noqa: F401  -- the import the real run needs (E17's lesson)
        todo = sum(max(0, N_CALLS - len(records.get(p, {}).get("calls", [])))
                   for _, p in CORPUS)
        print("corpus ok: %d drafts, %d calls each; %d call(s) to make; validate imports"
              % (len(CORPUS), N_CALLS, todo))
        return 0

    import validate
    for group, rel in CORPUS:
        path = ROOT / rel
        text = path.read_text(encoding="utf-8")
        rec = records.setdefault(rel, {"group": group, "bytes": len(text), "calls": []})
        while len(rec["calls"]) < N_CALLS:
            verdict, detail = validate.critique(text, {"kind": group}, str(REPO))
            if verdict == "inconclusive":
                verdict, detail = validate.critique(text, {"kind": group}, str(REPO))
            if verdict == "inconclusive" and not q5.transport_ok(validate):
                print("STOP: `claude -p` is not answering; nothing recorded for this "
                      "call -- wait for the reset and re-run.", file=sys.stderr)
                return 2
            rec["calls"].append(verdict)
            try:
                rec.setdefault("findings", []).append(json.loads(detail) if detail else [])
            except ValueError:
                rec.setdefault("findings", []).append([])
            RESULTS.write_text(json.dumps(records, indent=2) + "\n", encoding="utf-8")
            print("%-10s %-40s %s" % (group, rel.replace("drafts/E14/", ""), verdict))
    report(read_results(records))
    return 0


if __name__ == "__main__":
    sys.exit(main())
