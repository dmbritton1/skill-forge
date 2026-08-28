"""Save -> critique -> conjunct -> tiering, end to end (slice D2).
Run: python3 tests/test_validation_e2e.py
"""
import io
import json
import os
import pathlib
import sys
import tempfile
from contextlib import redirect_stderr, redirect_stdout

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
import ledger
import library
import save_skill
import sync
import trust
import validate

PLUGIN_ROOT = pathlib.Path(__file__).resolve().parent.parent

SKILL = """---
name: widget-flush
kind: skill
description: >
  Flush widgets before closing. Use when: closing a widget.
  Do NOT use when: the widget is read-only.
verification.command: python3 -m widget selfcheck
---
## Procedure
1. Call flush() before close().
## Verification
- `python3 -m widget selfcheck` exits 0.
"""


def in_sandbox(fn):
    old_home = os.environ["HOME"]
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["HOME"] = tmp
        try:
            fn(pathlib.Path(tmp))
        finally:
            os.environ["HOME"] = old_home


def ok_findings():
    return "\n".join(json.dumps(
        {"criterion": c, "ok": True, "evidence": "Call flush() before close().",
         "note": "n"}) for c in ("followable", "preconditions", "checkable"))


def bad_findings():
    # All three criteria must be answered or critique() reads the reply as
    # truncated and returns "inconclusive" (never recorded, per R12) rather
    # than reaching verdict_from at all -- an incomplete reply here would
    # test the truncation gate, not the promotion block this test is named
    # for. One criterion is "ok": False so verdict_from returns "fail".
    findings = [
        {"criterion": "followable", "ok": False,
         "evidence": "Call flush() before close().",
         "note": "close() is never defined"},
        {"criterion": "preconditions", "ok": True,
         "evidence": "Call flush() before close().", "note": "n"},
        {"criterion": "checkable", "ok": True,
         "evidence": "Call flush() before close().", "note": "n"},
    ]
    return "\n".join(json.dumps(f) for f in findings)


def save(home, spawned):
    p = home / "candidate.md"
    p.write_text(SKILL, encoding="utf-8")
    real = save_skill._spawn_validation
    save_skill._spawn_validation = lambda n, m: spawned.append((n, m))
    try:
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            rc = save_skill.main([str(p), "--scope", "global"])
    finally:
        save_skill._spawn_validation = real
    assert rc == 0, rc


def run_critique(reply, calls):
    real = validate.run_model

    def spy(prompt, *a, **k):
        calls.append(prompt)
        return reply

    validate.run_model = spy
    try:
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            assert validate.main(["critique", "--skill", "widget-flush"]) == 0
    finally:
        validate.run_model = real


def test_two_successes_without_critique_do_not_reach_trusted():
    def check(home):
        save(home, [])
        for i in range(2):
            ledger.log_event("detection", "widget-flush", outcome="success",
                             session="s%d" % i)
        sync.sync()
        row = [r for r in library.rows() if r["name"] == "widget-flush"][0]
        assert row["bucket"] == "working", row
        assert row["critique"] == "", row
    in_sandbox(check)


def test_critique_pass_plus_two_successes_reaches_trusted():
    def check(home):
        spawned = []
        save(home, spawned)
        assert spawned == [("widget-flush", "critique")], spawned
        calls = []
        run_critique(ok_findings(), calls)
        assert len(calls) == 1, "the model seam was never reached"
        assert "END SKILL TEXT" in calls[0]
        for i in range(2):
            ledger.log_event("detection", "widget-flush", outcome="success",
                             session="s%d" % i)
        sync.sync()
        row = [r for r in library.rows() if r["name"] == "widget-flush"][0]
        assert row["critique"] == "pass", row
        assert row["bucket"] == "trusted", row
    in_sandbox(check)


def test_editing_the_skill_voids_its_critique_and_drops_it_from_trusted():
    def check(home):
        save(home, [])
        calls = []
        run_critique(ok_findings(), calls)
        assert len(calls) == 1
        for i in range(2):
            ledger.log_event("detection", "widget-flush", outcome="success",
                             session="s%d" % i)
        sync.sync()
        assert [r for r in library.rows()
                if r["name"] == "widget-flush"][0]["bucket"] == "trusted"

        entry = [e for e in json.loads(
            (home / ".claude" / "skillforge" / "index.json").read_text()
        )["entries"] if e["name"] == "widget-flush"][0]
        p = pathlib.Path(entry["path"])
        edited = SKILL.replace("Call flush() before close().", "Do it differently.")
        p.write_text(edited, encoding="utf-8")
        trust.record("widget-flush", edited, "self")   # re-approved, new hash
        sync.sync()
        row = [r for r in library.rows() if r["name"] == "widget-flush"][0]
        assert row["critique"] == "", row
        assert row["bucket"] == "working", row
    in_sandbox(check)


def test_a_critique_that_finds_a_problem_blocks_promotion():
    def check(home):
        save(home, [])
        calls = []
        run_critique(bad_findings(), calls)
        assert len(calls) == 1
        for i in range(2):
            ledger.log_event("detection", "widget-flush", outcome="success",
                             session="s%d" % i)
        sync.sync()
        row = [r for r in library.rows() if r["name"] == "widget-flush"][0]
        assert row["critique"] == "fail", row
        assert row["bucket"] == "working", row
    in_sandbox(check)


if __name__ == "__main__":
    failures = 0
    for name in sorted(list(globals())):
        fn = globals()[name]
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("PASS " + name)
            except Exception as err:
                failures += 1
                print("FAIL %s: %r" % (name, err))
    sys.exit(1 if failures else 0)
