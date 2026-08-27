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
