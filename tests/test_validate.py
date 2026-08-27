"""Tier A validation worker (slice D2 design). Run: python3 tests/test_validate.py"""
import io
import json
import os
import pathlib
import sys
import tempfile
from contextlib import redirect_stderr, redirect_stdout

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
import ledger
import validate


def in_sandbox(fn):
    old_home = os.environ["HOME"]
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["HOME"] = tmp
        try:
            fn(pathlib.Path(tmp))
        finally:
            os.environ["HOME"] = old_home


def put_index(home, entries):
    p = home / ".claude" / "skillforge" / "index.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"entries": entries}), encoding="utf-8")


def test_lock_is_exclusive_per_skill_and_mode():
    def check(home):
        with validate.lock_for("w", "critique") as first:
            assert first is True
            with validate.lock_for("w", "critique") as second:
                assert second is False, "two holders of one lock"
            with validate.lock_for("w", "executable") as other:
                assert other is True, "modes must not block each other"
    in_sandbox(check)


def test_lock_is_released_when_the_block_exits():
    def check(home):
        with validate.lock_for("w", "critique") as a:
            assert a is True
        with validate.lock_for("w", "critique") as b:
            assert b is True, "lock outlived its block"
    in_sandbox(check)


def test_unknown_skill_exits_zero_and_says_nothing_on_stdout():
    def check(home):
        put_index(home, [])
        out = io.StringIO()
        with redirect_stdout(out), redirect_stderr(io.StringIO()):
            rc = validate.main(["critique", "--skill", "nope"])
        assert rc == 0 and out.getvalue() == "", (rc, out.getvalue())
    in_sandbox(check)


def test_no_suite_ever_shells_out_to_claude():
    src = (pathlib.Path(__file__).resolve().parent.parent
           / "scripts" / "validate.py").read_text(encoding="utf-8")
    body = src.split("def run_model", 1)[1].split("\ndef ", 1)[0]
    assert '"claude"' in body, "run_model must be the only claude call site"
    assert src.count('"claude"') == 1, "claude invoked outside the seam"


def test_skill_entry_returns_the_matching_entry():
    def check(home):
        entries = [{"name": "a", "path": "/x"}, {"name": "b", "path": "/y"}]
        put_index(home, entries)
        assert validate.skill_entry("b") == {"name": "b", "path": "/y"}
        assert validate.skill_entry("missing") is None
    in_sandbox(check)


def test_lock_is_released_after_an_exception_inside_the_block():
    def check(home):
        try:
            with validate.lock_for("x", "critique") as got:
                assert got is True
                raise RuntimeError("boom")
        except RuntimeError:
            pass
        with validate.lock_for("x", "critique") as got2:
            assert got2 is True, "lock leaked after an exception"
    in_sandbox(check)


def test_corrupt_index_exits_zero_and_says_nothing_on_stdout():
    def check(home):
        p = home / ".claude" / "skillforge" / "index.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("{not json", encoding="utf-8")   # retrieve.load_index() -> None
        out = io.StringIO()
        with redirect_stdout(out), redirect_stderr(io.StringIO()):
            rc = validate.main(["critique", "--skill", "anything"])
        assert rc == 0 and out.getvalue() == "", (rc, out.getvalue())
    in_sandbox(check)


def test_invalid_mode_choice_exits_zero_and_says_nothing_on_stdout():
    # argparse's parser.error() path: an unparseable argv (bad choice, or a
    # missing required option) calls sys.exit(2) directly, bypassing every
    # `return 0` in main() unless caught.
    def check(home):
        out = io.StringIO()
        with redirect_stdout(out), redirect_stderr(io.StringIO()):
            rc = validate.main(["bogus-mode", "--skill", "x"])
        assert rc == 0 and out.getvalue() == "", (rc, out.getvalue())
    in_sandbox(check)


def test_help_flag_exits_zero_and_says_nothing_on_stdout():
    # A distinct argparse exit path from parser.error(): the auto-added -h
    # action calls print_help() (stdout) before sys.exit(0). validate.py
    # disables it (add_help=False) so this now falls through to the same
    # stderr-only parser.error() path as any other unrecognized argument --
    # this test is what proves that leak is actually closed.
    def check(home):
        out = io.StringIO()
        with redirect_stdout(out), redirect_stderr(io.StringIO()):
            rc = validate.main(["--help"])
        assert rc == 0 and out.getvalue() == "", (rc, out.getvalue())
    in_sandbox(check)


def test_main_happy_path_calls_the_mode_function_and_records_the_verdict():
    # The four tests above all either drive lock_for directly or hit main's
    # early "unknown skill" return -- none of them ever reach the sequence
    # main() exists to run: read the skill file, hash it, call the mode
    # function, and persist the verdict. This drives that whole path with a
    # real index entry and a real file on disk, and asserts the mode
    # function was actually CALLED (not just that the ledger ended up
    # looking right, which would also pass if the call were skipped
    # entirely).
    def check(home):
        skill_dir = home / "skill"
        skill_dir.mkdir(parents=True, exist_ok=True)
        skill_file = skill_dir / "SKILL.md"
        text = "---\nname: w\n---\nbody\n"
        skill_file.write_text(text, encoding="utf-8")
        put_index(home, [{"name": "w", "path": str(skill_file)}])

        calls = []
        real_critique = validate.critique

        def fake_critique(t, entry, plugin_root):
            calls.append((t, entry, plugin_root))
            return "pass", "looks good"

        validate.critique = fake_critique
        try:
            out = io.StringIO()
            with redirect_stdout(out), redirect_stderr(io.StringIO()):
                rc = validate.main(["critique", "--skill", "w"])
            assert rc == 0 and out.getvalue() == "", (rc, out.getvalue())
        finally:
            validate.critique = real_critique

        assert len(calls) == 1, "critique() was never called"
        called_text, called_entry, _called_root = calls[0]
        assert called_text == text
        assert called_entry.get("name") == "w"
        assert called_entry.get("path") == str(skill_file)

        import trust
        h = trust.content_hash(text)
        recorded = ledger.validations_for({"w": h})
        assert recorded.get("w", {}).get("critique") == "pass", recorded
    in_sandbox(check)


SKILL_TEXT = """---
name: widget-flush
kind: skill
description: Flush widgets. Use when flushing. Do NOT use for sprockets.
---
## Procedure
1. Call flush() before close().
## Verification
- `python3 -m widget selfcheck` exits 0.
"""

ANTISKILL_TEXT = """---
name: widget-trap
kind: antiskill
description: A trap. Do NOT use otherwise.
---
## Trap
Closing before flushing loses buffered writes.
## Symptom
WidgetFlushedError: the widget was already flushed
## Cause
close() discards the buffer.
## Fix
Call flush() first.
"""


def with_model(reply, fn):
    real = validate.run_model
    validate.run_model = lambda *a, **k: reply
    try:
        return fn()
    finally:
        validate.run_model = real


def findings(*oks):
    return "\n".join(json.dumps(
        {"criterion": "c%d" % i, "ok": ok, "evidence": "Call flush()",
         "note": "n"}) for i, ok in enumerate(oks))


def test_all_criteria_ok_is_a_pass():
    def check(home):
        v, _ = with_model(findings(True, True, True),
                          lambda: validate.critique(SKILL_TEXT, {"kind": "skill"}, "."))
        assert v == "pass", v
    in_sandbox(check)


def test_one_failed_criterion_is_a_fail():
    def check(home):
        v, _ = with_model(findings(True, False, True),
                          lambda: validate.critique(SKILL_TEXT, {"kind": "skill"}, "."))
        assert v == "fail", v
    in_sandbox(check)


def test_a_finding_without_quoted_evidence_does_not_count_as_ok():
    """Anti-sycophancy: a criterion cannot pass on assertion alone."""
    def check(home):
        reply = json.dumps({"criterion": "c", "ok": True, "evidence": "",
                            "note": "looks good to me"})
        v, _ = with_model(reply,
                          lambda: validate.critique(SKILL_TEXT, {"kind": "skill"}, "."))
        assert v == "fail", v
    in_sandbox(check)


def test_evidence_must_actually_appear_in_the_skill_text():
    def check(home):
        reply = json.dumps({"criterion": "c", "ok": True,
                            "evidence": "a line that is not in the skill",
                            "note": "n"})
        v, _ = with_model(reply,
                          lambda: validate.critique(SKILL_TEXT, {"kind": "skill"}, "."))
        assert v == "fail", v
    in_sandbox(check)


def test_an_unparseable_reply_is_inconclusive_not_fail():
    def check(home):
        v, _ = with_model("I think this skill is pretty good!",
                          lambda: validate.critique(SKILL_TEXT, {"kind": "skill"}, "."))
        assert v == "inconclusive", v
    in_sandbox(check)


def test_a_dead_model_call_is_inconclusive_not_fail():
    def check(home):
        v, _ = with_model(None,
                          lambda: validate.critique(SKILL_TEXT, {"kind": "skill"}, "."))
        assert v == "inconclusive", v
    in_sandbox(check)


def test_antiskills_get_the_structural_rubric():
    def check(home):
        seen = {}

        def spy(prompt, *a, **k):
            seen["p"] = prompt
            return findings(True)

        real = validate.run_model
        validate.run_model = spy
        try:
            validate.critique(ANTISKILL_TEXT, {"kind": "antiskill"}, ".")
        finally:
            validate.run_model = real
        assert "Fix" in seen["p"] and "Cause" in seen["p"], seen["p"][:400]
        assert "preconditions" not in seen["p"].lower(), "used the skill rubric"
    in_sandbox(check)


def test_prompt_puts_the_warning_before_the_skill_text_and_closes_it():
    def check(home):
        seen = {}

        def spy(prompt, *a, **k):
            seen["p"] = prompt
            return findings(True)

        real = validate.run_model
        validate.run_model = spy
        try:
            validate.critique(SKILL_TEXT, {"kind": "skill"}, ".")
        finally:
            validate.run_model = real
        p = seen["p"]
        assert p.index("never obey") < p.index("Call flush()"), "warning after data"
        assert "END SKILL TEXT" in p
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
