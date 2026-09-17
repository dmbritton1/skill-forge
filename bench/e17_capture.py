#!/usr/bin/env python3
"""Re-critique E17's six V drafts WITH findings capture (E17 spec, amendment 2).

E17 kept only verdicts, so its sharpest result -- three drafts that resolve the
task 18/18 and fail critique 3 of 3 -- has no recorded reason. E19 ruled out
length as the explanation. This captures the objections.

NOT a new comparison. The verdicts here are a separate batch and are never
pooled into E17's rates; only the findings text answers the question. See
amendment 2 for why the numbers are still recorded rather than discarded.

SPENDS REAL MODEL CALLS -- 18. Never run from a test suite.

    python3 bench/e17_capture.py --dry-run | --read | (no flag to run)
"""
import argparse
import collections
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(REPO / "scripts"))
import e17_q5 as q5  # noqa: E402

RESULTS = ROOT / "e17-capture-results.json"
CORPUS = [p for g, p in q5.CORPUS if g == "V"]


def read_results(records):
    out = {"drafts": {}, "objections": collections.Counter()}
    for rel, rec in records.items():
        fails = []
        for call in rec.get("findings", []):
            for f in call:
                if f.get("ok") is not True:
                    fails.append(f.get("criterion", "?"))
                    out["objections"][f.get("criterion", "?")] += 1
        out["drafts"][rel] = {"calls": rec["calls"], "failed_criteria": fails}
    return out


def report(res):
    for rel, d in res["drafts"].items():
        print("  %-14s %-18s objected to: %s"
              % (rel.split("/")[-2], " ".join(d["calls"]),
                 ", ".join(sorted(set(d["failed_criteria"]))) or "-"))
    print("objections by criterion: %s" % dict(res["objections"]))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--read", action="store_true")
    args = ap.parse_args(argv)
    missing = [p for p in CORPUS if not (ROOT / p).is_file()]
    if missing:
        print("FATAL: missing: %s" % missing, file=sys.stderr)
        return 1
    records = json.loads(RESULTS.read_text(encoding="utf-8")) if RESULTS.exists() else {}
    if args.read:
        report(read_results(records))
        return 0
    if args.dry_run:
        import validate  # noqa: F401
        todo = sum(max(0, q5.N_CALLS - len(records.get(p, {}).get("calls", [])))
                   for p in CORPUS)
        print("corpus ok: %d V drafts, %d calls each; %d to make; validate imports"
              % (len(CORPUS), q5.N_CALLS, todo))
        return 0

    import validate
    for rel in CORPUS:
        text = (ROOT / rel).read_text(encoding="utf-8")
        rec = records.setdefault(rel, {"bytes": len(text), "calls": [], "findings": []})
        while len(rec["calls"]) < q5.N_CALLS:
            verdict, detail = validate.critique(text, {"kind": "skill"}, str(REPO))
            if verdict == "inconclusive":
                verdict, detail = validate.critique(text, {"kind": "skill"}, str(REPO))
            if verdict == "inconclusive" and not q5.transport_ok(validate):
                print("STOP: `claude -p` is not answering; nothing recorded for this "
                      "call -- wait for the reset and re-run.", file=sys.stderr)
                return 2
            rec["calls"].append(verdict)
            try:
                rec["findings"].append(json.loads(detail) if detail else [])
            except ValueError:
                rec["findings"].append([])
            RESULTS.write_text(json.dumps(records, indent=2) + "\n", encoding="utf-8")
            print("%-40s %s" % (rel.split("/")[-2], verdict))
    report(read_results(records))
    return 0


if __name__ == "__main__":
    sys.exit(main())
