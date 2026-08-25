"""Breadcrumb to delivered draft, through the real hook entry points.
Run: python3 tests/test_capture_e2e.py
"""
import io
import json
import os
import pathlib
import sys
import tempfile
from contextlib import redirect_stdout

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
import detect
import draft
import ledger
import reconcile

PLUGIN_ROOT = pathlib.Path(__file__).resolve().parent.parent

DRAFTED = """---
name: pool-close-order
kind: skill
description: >
  Flush widgets before closing the pool.
  Use when: a widget write races pool teardown.
  Do NOT use when: the pool is single-threaded.
verification.command: "python3 tests/test_widget.py"
fingerprints:
  - "await widget.flush({ force: true })"
  - "pool.close(after=widget.flush)"
---

## Procedure
1. Flush every widget, then close the pool.

## Verification
- `python3 tests/test_widget.py` should exit 0.
"""


def in_sandbox(fn):
    old_home = os.environ["HOME"]
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["HOME"] = tmp
        try:
            fn(pathlib.Path(tmp))
        finally:
            os.environ["HOME"] = old_home


def empty_triggers(home):
    p = home / ".claude" / "skillforge" / "triggers.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"symptoms": [], "verifications": []}),
                 encoding="utf-8")
    (p.parent / "index.json").write_text(json.dumps({"entries": []}),
                                         encoding="utf-8")


def bash(command, is_error):
    detect.run({"session_id": "s1", "tool_name": "Bash",
                "tool_input": {"command": command},
                "tool_response": {"is_error": is_error, "stdout": "..."}})


def write_transcript(home):
    """A stand-in transcript file for the drafter to read as evidence.

    draft.transcript_slice() returns "" for a missing/empty path, and
    draft.produce() refuses to call the model on empty evidence (by
    design -- a model call with nothing to distill invents a skill). The
    lines here carry no parseable `timestamp`, so transcript_slice falls
    through to its undated tail fallback and returns this text whole,
    regardless of the signal's since/until window.
    """
    p = home / "transcript.jsonl"
    p.write_text("widget flush before pool close, then teardown\n",
                 encoding="utf-8")
    return str(p)


def inline_drafter(reply):
    """Runs the spawned argv in-process instead of detaching, with a stub model."""
    def spawn(argv, cwd):
        real = draft.run_model
        draft.run_model = lambda prompt, cwd_, model=None, timeout=None: reply
        try:
            args = argv[2:] + ["--plugin-root", str(PLUGIN_ROOT)]
            assert draft.main(args) == 0
        finally:
            draft.run_model = real
    return spawn


def stop(**extra):
    data = {"session_id": "s1", "cwd": ".", "hook_event_name": "Stop"}
    data.update(extra)
    out = io.StringIO()
    with redirect_stdout(out):
        reconcile.run(data)
    return out.getvalue()


def with_spawner(spawn, fn):
    real = reconcile._spawn
    reconcile._spawn = spawn
    try:
        return fn()
    finally:
        reconcile._spawn = real


def test_struggle_becomes_a_delivered_draft():
    def check(home):
        empty_triggers(home)
        bash("python3 tests/test_widget.py", True)
        bash("python3 tests/test_widget.py", True)
        bash("python3 tests/test_widget.py", False)

        # First Stop: the signal fires and the drafter runs (inline here).
        transcript = write_transcript(home)
        assert with_spawner(inline_drafter(DRAFTED),
                             lambda: stop(transcript_path=transcript)) == ""

        con = ledger.connect()
        try:
            status, name = con.execute(
                "SELECT status, name FROM drafts").fetchone()
        finally:
            con.close()
        assert (status, name) == ("ready", "pool-close-order")

        # Second Stop: the finished draft interrupts.
        payload = json.loads(with_spawner(inline_drafter(DRAFTED), stop))
        assert payload["decision"] == "block"
        assert "pool-close-order" in payload["reason"]

        draft_file = draft.drafts_dir() / "1.md"
        assert draft_file.read_text(encoding="utf-8") == DRAFTED
        assert str(draft_file) in payload["reason"]
    in_sandbox(check)


def test_an_aborted_draft_never_interrupts():
    def check(home):
        empty_triggers(home)
        for ok in (False, False, True):
            bash("python3 tests/test_widget.py", not ok)
        transcript = write_transcript(home)
        with_spawner(inline_drafter("ABORT: a fresh Claude would know this"),
                     lambda: stop(transcript_path=transcript))
        assert with_spawner(inline_drafter("unused"), stop) == ""
        con = ledger.connect()
        try:
            assert con.execute("SELECT status FROM drafts").fetchone()[0] == "aborted"
        finally:
            con.close()
    in_sandbox(check)


def test_a_one_shot_failure_never_drafts():
    def check(home):
        empty_triggers(home)
        bash("python3 tests/test_widget.py", True)
        bash("python3 tests/test_widget.py", False)
        assert with_spawner(inline_drafter(DRAFTED), stop) == ""
        con = ledger.connect()
        try:
            assert con.execute("SELECT COUNT(*) FROM drafts").fetchone()[0] == 0
        finally:
            con.close()
    in_sandbox(check)


def test_session_end_clears_the_breadcrumbs_but_keeps_the_draft():
    def check(home):
        empty_triggers(home)
        for ok in (False, False, True):
            bash("python3 tests/test_widget.py", not ok)
        transcript = write_transcript(home)
        with_spawner(inline_drafter(DRAFTED), lambda: stop(transcript_path=transcript))
        with_spawner(inline_drafter(DRAFTED), lambda: reconcile.run(
            {"session_id": "s1", "cwd": ".", "hook_event_name": "SessionEnd"}))
        con = ledger.connect()
        try:
            assert con.execute("SELECT COUNT(*) FROM signals").fetchone()[0] == 0
            assert con.execute("SELECT COUNT(*) FROM drafts").fetchone()[0] == 1
        finally:
            con.close()
    in_sandbox(check)


if __name__ == "__main__":
    for name, fn in sorted(list(globals().items())):
        if name.startswith("test_") and callable(fn):
            fn()
            print("PASS %s" % name)
