#!/usr/bin/env python3
"""Measure critique's calibration against a corpus with known ground truth.

SPENDS REAL MODEL CALLS -- one `claude -p` turn per case. Never run from a
test suite; `tests/` is forbidden from invoking a model, and this is why the
corpus lives here instead.

    python3 bench/critique-calibration/run.py                  # all cases
    python3 bench/critique-calibration/run.py 07 01            # by prefix
    python3 bench/critique-calibration/run.py --save before    # keep the raw findings

The point is not the pass rate. It is that a rubric change can be measured
against fixed inputs whose correct answers were established by reading the
code and, for case 07, by running git both ways. Tuning a rubric on fresh
hand-written examples is how you talk yourself into whatever you already
believed.
"""
import argparse
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent
REPO = ROOT.parent.parent
sys.path.insert(0, str(REPO / "scripts"))
import validate                                            # noqa: E402


def load_cases(prefixes):
    spec = json.loads((ROOT / "expected.json").read_text(encoding="utf-8"))
    out = []
    for path in sorted((ROOT / "cases").glob("*.md")):
        name = path.stem
        if prefixes and not any(name.startswith(p) for p in prefixes):
            continue
        out.append((name, path.read_text(encoding="utf-8"), spec["cases"][name]))
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("prefix", nargs="*", help="run only cases starting with these")
    ap.add_argument("--save", help="write raw findings to results-<label>.json")
    args = ap.parse_args(argv)

    cases = load_cases(args.prefix)
    if not cases:
        print("no cases matched", file=sys.stderr)
        return 2

    results, agree = {}, 0
    for name, text, spec in cases:
        # kind drives which rubric critique selects; every corpus case is a
        # skill, not an anti-skill.
        verdict, detail = validate.critique(text, {"kind": "skill"}, str(REPO))
        try:
            findings = json.loads(detail) if detail else []
        except ValueError:
            findings = []
        ok = verdict == spec["expect"]
        agree += ok
        results[name] = {"expect": spec["expect"], "got": verdict,
                         "role": spec["role"], "findings": findings}
        passed = sum(1 for f in findings if f.get("ok") is True)
        print("%-30s expect=%-4s got=%-12s %s  (%d/%d criteria)"
              % (name, spec["expect"], verdict,
                 "OK " if ok else "MISMATCH", passed, len(findings)))
        if not ok:
            for f in findings:
                if f.get("ok") is not True:
                    print("      [%s] %s" % (f.get("criterion", "?"),
                                             str(f.get("note", ""))[:150]))

    print("\n%d/%d cases match ground truth" % (agree, len(cases)))
    if args.save:
        out = ROOT / ("results-%s.json" % args.save)
        out.write_text(json.dumps(results, indent=2), encoding="utf-8")
        print("raw findings: %s" % out)
    # Non-zero on any mismatch so a change that regresses the corpus is loud.
    return 0 if agree == len(cases) else 1


if __name__ == "__main__":
    sys.exit(main())
