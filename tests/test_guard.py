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


class CountingStdin:
    """Counts reads so the assertion survives the hooks' own catch-all.

    An exception-raising stub cannot prove ordering here: detect, reconcile,
    and retrieve wrap their stdin read in `except Exception`, which would
    swallow the raise and still return 0 -- so the test would pass with or
    without the guard.
    """

    def __init__(self):
        self.reads = 0

    def read(self, *args):
        self.reads += 1
        return ""


def in_drafter(fn):
    old_home = os.environ["HOME"]
    os.environ["SKILLFORGE_DRAFTING"] = "1"
    old_stdin = sys.stdin
    stdin = CountingStdin()
    sys.stdin = stdin
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["HOME"] = tmp
        try:
            fn(pathlib.Path(tmp), stdin)
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
    def check(home, stdin):
        silent(detect.main, [])
        assert stdin.reads == 0
    in_drafter(check)


def test_retrieve_is_inert():
    def check(home, stdin):
        silent(retrieve.main, [])
        assert stdin.reads == 0
    in_drafter(check)


def test_reconcile_is_inert():
    def check(home, stdin):
        silent(reconcile.main, [])
        assert stdin.reads == 0
    in_drafter(check)


def test_sync_is_inert():
    def check(home, stdin):
        silent(sync.main, [])
        # sync reads no stdin, so the proof is that it wrote no derived state
        assert not (home / ".claude" / "skillforge" / "index.json").exists()
        assert stdin.reads == 0
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
