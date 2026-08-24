"""Every hook is inert inside a drafter subprocess (slice D1 design 7).
Run: python3 tests/test_guard.py
"""
import io
import os
import pathlib
import sys
import tempfile
from contextlib import redirect_stdout

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
import detect
import reconcile
import retrieve
import sync


class ExplodingStdin:
    """Proves the guard returned before the hook touched its payload."""

    def read(self, *args):
        raise AssertionError("hook read stdin inside a drafter")


def in_drafter(fn):
    old_home = os.environ["HOME"]
    os.environ["SKILLFORGE_DRAFTING"] = "1"
    old_stdin = sys.stdin
    sys.stdin = ExplodingStdin()
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["HOME"] = tmp
        try:
            fn(pathlib.Path(tmp))
        finally:
            sys.stdin = old_stdin
            os.environ["HOME"] = old_home
            del os.environ["SKILLFORGE_DRAFTING"]


def silent(main, argv):
    out = io.StringIO()
    with redirect_stdout(out):
        rc = main(argv)
    assert rc == 0, rc
    assert out.getvalue() == "", out.getvalue()


def test_detect_is_inert():
    in_drafter(lambda home: silent(detect.main, []))


def test_retrieve_is_inert():
    in_drafter(lambda home: silent(retrieve.main, []))


def test_reconcile_is_inert():
    in_drafter(lambda home: silent(reconcile.main, []))


def test_sync_is_inert():
    def check(home):
        silent(sync.main, [])
        # sync reads no stdin, so the proof is that it wrote no derived state
        assert not (home / ".claude" / "skillforge" / "index.json").exists()
    in_drafter(check)


def test_hooks_still_work_without_the_variable():
    old_stdin = sys.stdin
    sys.stdin = io.StringIO("{}")
    old_home = os.environ["HOME"]
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["HOME"] = tmp
        try:
            out = io.StringIO()
            with redirect_stdout(out):
                assert sync.main([]) == 0
            assert (pathlib.Path(tmp) / ".claude" / "skillforge" / "index.json").exists()
        finally:
            os.environ["HOME"] = old_home
            sys.stdin = old_stdin


if __name__ == "__main__":
    for name, fn in sorted(list(globals().items())):
        if name.startswith("test_") and callable(fn):
            fn()
            print("PASS %s" % name)
