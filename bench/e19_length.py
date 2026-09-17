#!/usr/bin/env python3
"""E19: does critique's verdict move with length when content is held fixed?

docs/superpowers/specs/2026-09-16-e19-length-manipulation-design.md

E17 and E18 could not separate length from outcome by choosing a corpus --
there is no more natural material, every short skill in the repository is
either an anti-skill or one of E14's two. E19 separates them by MANIPULATING
length: five short drafts, each critiqued bare and again with a constant
1395-byte neutral block appended, in one batch.

The treatment is identical for every draft. The spec's section 2 states the
irreducible flaw -- a document cannot be lengthened without being changed --
and what the paired design does and does not buy.

Outcome is not re-measured: the question is whether the VERDICT moves, so this
costs no bench session. The padded forms were never run on the task and nothing
here claims they would still resolve it.

SPENDS REAL MODEL CALLS -- 30. Never run from a test suite.

    python3 bench/e19_length.py --dry-run
    python3 bench/e19_length.py
    python3 bench/e19_length.py --read
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
import e17_q5 as q5                              # noqa: E402
from e13_outcome_read import fisher_two_sided    # noqa: E402

RESULTS = ROOT / "e19-length-results.json"
PAD = ROOT / "fixtures" / "e19_pad.md"
N_CALLS = q5.N_CALLS
CORPUS = ([("distilled/C/learn-nogate/%d/SKILL.md" % i) for i in (1, 2, 3)] +
          ["drafts/E14/e14-quote-gate-rewrap-%s.md" % s for s in ("sf", "sw")])
ARMS = ("bare", "padded")


def form(rel, arm):
    """The exact text critiqued for one (draft, arm)."""
    text = (ROOT / rel).read_text(encoding="utf-8")
    return text if arm == "bare" else text + PAD.read_text(encoding="utf-8")


def band(delta):
    """Spec section 3."""
    if delta <= Fraction(-3, 10):
        return "length is implicated"
    if delta >= Fraction(3, 10):
        return "length is not the driver -- E17's direction survives"
    return "no large effect of length at this size"


def read_results(records):
    cells = {a: [0, 0] for a in ARMS}
    pairs, unanimous = {}, 0
    for key, rec in records.items():
        rel, arm = key.rsplit("|", 1)
        graded = [c for c in rec["calls"] if c != "inconclusive"]
        cells[arm][0] += sum(1 for c in graded if c == "pass")
        cells[arm][1] += len(graded)
        pairs.setdefault(rel, {})[arm] = rec["calls"]
        if len(rec["calls"]) >= N_CALLS and len(set(rec["calls"])) == 1:
            unanimous += 1
    out = {"cells": cells, "pairs": pairs, "unanimous": unanimous,
           "forms": len(records), "measures": None}
    complete = (len(records) >= len(CORPUS) * len(ARMS)
                and all(len(r["calls"]) >= N_CALLS for r in records.values()))
    if not complete:
        out["reason"] = "not every form has been critiqued yet"
        return out
    (bp, bn), (pp, pn) = cells["bare"], cells["padded"]
    if not bn or not pn:
        out["reason"] = "an arm has no graded call"
        return out
    delta = Fraction(pp, pn) - Fraction(bp, bn)
    out["measures"] = {"bare": [bp, bn], "padded": [pp, pn],
                       "delta": round(float(delta), 2), "reading": band(delta),
                       "p": fisher_two_sided(pp, pn - pp, bp, bn - bp)}
    out["reason"] = ""
    return out


def report(res):
    print("  %-38s %-18s %s" % ("draft", "bare", "padded"))
    for rel, arms in res["pairs"].items():
        print("  %-38s %-18s %s"
              % (rel.split("/")[-2] if "learn" in rel else rel.split("/")[-1],
                 " ".join(arms.get("bare", [])), " ".join(arms.get("padded", []))))
    print("stability: %d of %d forms unanimous over %d calls"
          % (res["unanimous"], res["forms"], N_CALLS))
    m = res["measures"]
    if not m:
        print("not readable: %s" % res["reason"])
        return
    print("bare %d/%d  padded %d/%d  delta = %+.2f -- %s (Fisher p = %.3f)"
          % (m["bare"][0], m["bare"][1], m["padded"][0], m["padded"][1],
             m["delta"], m["reading"], m["p"]))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--read", action="store_true")
    args = ap.parse_args(argv)
    missing = [p for p in CORPUS if not (ROOT / p).is_file()] + (
        [] if PAD.is_file() else [str(PAD)])
    if missing:
        print("FATAL: missing: %s" % missing, file=sys.stderr)
        return 1
    records = json.loads(RESULTS.read_text(encoding="utf-8")) if RESULTS.exists() else {}
    if args.read:
        report(read_results(records))
        return 0
    if args.dry_run:
        import validate  # noqa: F401  -- the import the real run needs (E17's lesson)
        todo = sum(max(0, N_CALLS - len(records.get("%s|%s" % (r, a), {}).get("calls", [])))
                   for r in CORPUS for a in ARMS)
        print("corpus ok: %d drafts x %d arms, %d calls each; %d call(s) to make; "
              "validate imports" % (len(CORPUS), len(ARMS), N_CALLS, todo))
        for rel in CORPUS:
            print("  %-40s %5d -> %5d bytes"
                  % (rel.split("/")[-1], len(form(rel, "bare")), len(form(rel, "padded"))))
        return 0

    import validate
    # Interleaved by ARM within each draft, so a drift across the run cannot
    # land entirely on one arm of a pair.
    for rel in CORPUS:
        for arm in ARMS:
            key = "%s|%s" % (rel, arm)
            text = form(rel, arm)
            rec = records.setdefault(key, {"arm": arm, "bytes": len(text), "calls": []})
            while len(rec["calls"]) < N_CALLS:
                verdict, detail = validate.critique(text, {"kind": "skill"}, str(REPO))
                if verdict == "inconclusive":
                    verdict, detail = validate.critique(text, {"kind": "skill"}, str(REPO))
                if verdict == "inconclusive" and not q5.transport_ok(validate):
                    print("STOP: `claude -p` is not answering; nothing recorded for "
                          "this call -- wait for the reset and re-run.", file=sys.stderr)
                    return 2
                rec["calls"].append(verdict)
                try:
                    rec.setdefault("findings", []).append(
                        json.loads(detail) if detail else [])
                except ValueError:
                    rec.setdefault("findings", []).append([])
                RESULTS.write_text(json.dumps(records, indent=2) + "\n", encoding="utf-8")
                print("%-8s %-40s %s" % (arm, rel.split("/")[-1], verdict))
    report(read_results(records))
    return 0


if __name__ == "__main__":
    sys.exit(main())
