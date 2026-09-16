#!/usr/bin/env python3
"""E16 pre-flight: build each candidate's author task and decide its graded tests.

docs/superpowers/specs/2026-09-16-e16-author-traps-design.md, section 2.

Zero sessions. The method is E13's, reused by import rather than copied: each
candidate's fix-commit test file runs three ways against the parent commit's
code -- with the stub, with the parent's original function (the historical
bug), and with the fix's changed definitions transplanted in -- and the graded
set is every test that fails under the stub and passes with the fix.

ONE rule differs, and it is pre-registered in spec section 2.1. E13 proved the
tests catch the historical bug using the tests the fix ADDED. Candidate F's fix
records its bug by adding a line to an EXISTING test, so its added set is empty
and E13's rules would call it invalid for a reason that says nothing about the
trap. E16 uses the tests the fix added OR CHANGED: a test whose body the fix
rewrote encodes the fixed behaviour exactly as well as a new one does.
"""
import argparse
import ast
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import e13_preflight as pf  # noqa: E402  -- one pre-flight method, not two

SPEC = "docs/superpowers/specs/2026-09-16-e16-author-traps-design.md"

CANDIDATES = {
    # F: tests/test_reconcile.py's runner aborts at the first failure, so the
    # task grades with run_named_tests.py (own_runner False), as E13's D did.
    "F": {"id": "sf-author-read-markers", "fix": "ea4c47f", "source": "scripts/reconcile.py",
          "test_path": "tests/test_reconcile.py", "stub": "bench/stubs/stub_read_markers.py",
          "functions": ["read_markers"], "own_runner": False, "verbatim_docstring": True},
    # G: tests/test_ledger.py catches each test's failure, so it runs itself.
    "G": {"id": "sf-author-event-totals", "fix": "58ce279", "source": "scripts/ledger.py",
          "test_path": "tests/test_ledger.py", "stub": "bench/stubs/stub_event_totals.py",
          "functions": ["event_totals"], "own_runner": True, "verbatim_docstring": True},
}


def _test_bodies(src):
    lines = src.splitlines(keepends=True)
    return {n.name: "".join(lines[n.lineno - 1:n.end_lineno])
            for n in ast.parse(src).body
            if isinstance(n, ast.FunctionDef) and n.name.startswith("test_")}


def fix_touched(parent_test_src, fix_test_src):
    """Test names the fix added or whose body it changed (spec section 2.1)."""
    before, after = _test_bodies(parent_test_src), _test_bodies(fix_test_src)
    return {n for n, text in after.items() if before.get(n) != text}


def task_entry(letter, cand, graded, sigs):
    entry = pf.task_entry(letter, cand, graded, sigs)
    entry["selection_rule"] = (
        "E16 candidate %s (%s). No skill yet: control screen only. Graded tests "
        "decided by bench/e16_preflight.py." % (letter, SPEC))
    return entry


def main(argv=None):
    import run as bench_run
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--only", action="append", choices=sorted(CANDIDATES))
    ap.add_argument("--write", action="store_true",
                    help="write valid candidates into bench/tasks.json")
    args = ap.parse_args(argv)
    letters = args.only or sorted(CANDIDATES)
    work = Path(os.path.realpath(tempfile.mkdtemp(prefix="e16-preflight-")))
    bench_run.WORK = work
    valid = {}
    try:
        for letter in letters:
            cand = CANDIDATES[letter]
            parent_src = pf._git("show", "%s~1:%s" % (cand["fix"], cand["source"]))
            touched = fix_touched(
                pf._git("show", "%s~1:%s" % (cand["fix"], cand["test_path"])),
                pf._git("show", "%s:%s" % (cand["fix"], cand["test_path"])))
            stub, stub_dest = pf.run_variant(cand, "stub", work)
            original, _ = pf.run_variant(cand, "original", work)
            fix, _ = pf.run_variant(cand, "fix", work)
            doc_ok = pf.docstrings_match(
                (stub_dest / cand["source"]).read_text(encoding="utf-8"),
                parent_src, cand["functions"])
            graded, problems = pf.assess(stub, original, fix, touched, doc_ok)
            print("=== %s  %s  (fix %s)" % (letter, cand["id"], cand["fix"]))
            print("  stub:     %s" % pf._summary(stub))
            print("  original: %s" % pf._summary(original))
            print("  fix:      %s" % pf._summary(fix))
            print("  tests the fix added or changed: %s" % sorted(touched))
            print("  graded (%d): %s" % (len(graded), graded))
            if problems:
                print("  INVALID: " + "; ".join(problems))
            else:
                print("  VALID")
                valid[letter] = task_entry(letter, cand, graded,
                                           pf.signatures(parent_src, cand["functions"]))
    finally:
        shutil.rmtree(str(work), ignore_errors=True)
    if args.write and valid:
        pf.write_tasks(valid.values())
    return 0 if len(valid) == len(letters) else 1


if __name__ == "__main__":
    sys.exit(main())
