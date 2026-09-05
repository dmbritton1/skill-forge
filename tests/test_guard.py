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

# test_hooks_still_work_without_the_variable calls the REAL sync.main([]),
# which schedules validation runs. It is safe today only because the temp HOME
# has no skills -- a property of the fixture, not of this test. Stubbed inert
# at module scope so the guarantee is structural, exactly as tests/test_sync.py
# and tests/test_validation_e2e.py do it.
sync._spawn_validation = lambda name, mode: None


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


def registered_hooks():
    """Every `scripts/<name>.py` that hooks/hooks.json actually registers."""
    import json
    import re
    root = pathlib.Path(__file__).resolve().parent.parent
    spec = json.loads((root / "hooks" / "hooks.json").read_text(encoding="utf-8"))
    names = set()
    for groups in spec.get("hooks", {}).values():
        for group in groups:
            for hook in group.get("hooks", []):
                m = re.search(r"scripts/(\w+)\.py", hook.get("command", ""))
                if m:
                    names.add(m.group(1))
    return sorted(names)


def _main_block(source):
    """The `if __name__ == "__main__":` node of a module, or None."""
    import ast
    for node in ast.parse(source).body:
        if not isinstance(node, ast.If):
            continue
        t = node.test
        if (isinstance(t, ast.Compare) and isinstance(t.left, ast.Name)
                and t.left.id == "__name__"):
            return node
    return None


def test_no_hook_touches_argv_at_module_scope():
    """The reload test counts stdin reads and cannot see argv at all.

    sys.argv is a list, not a stream, so there is nothing to instrument -- but
    reading it at module scope is statically visible, and it is the other half
    of the import-time breakage step 4 warns about: a hook that parses argv
    when the module loads has already acted before main()'s guard runs.
    """
    import ast
    root = pathlib.Path(__file__).resolve().parent.parent
    for name in registered_hooks():
        tree = ast.parse((root / "scripts" / ("%s.py" % name)).read_text(encoding="utf-8"))
        for node in tree.body:                     # module scope only
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue
            for sub in ast.walk(node):
                bad = (isinstance(sub, ast.Attribute) and sub.attr == "argv"
                       and isinstance(sub.value, ast.Name) and sub.value.id == "sys")
                assert not bad, (
                    "%s reads sys.argv at module scope, before main()'s guard"
                    " can run" % name)


def test_no_hook_does_work_before_main():
    """A helper called at INVOCATION time escapes the guard just as an
    import-time one does, and the reload test cannot see it: reloading a
    module never executes its `__main__` block.

    Checked statically rather than by running the script, because these
    suites do not spawn real subprocesses -- and the property is static
    anyway: the entry point must hand straight to main(), so that main()'s
    first statement really is the first thing that runs.
    """
    import ast
    root = pathlib.Path(__file__).resolve().parent.parent
    for name in registered_hooks():
        src = (root / "scripts" / ("%s.py" % name)).read_text(encoding="utf-8")
        block = _main_block(src)
        assert block is not None, "%s has no __main__ block" % name
        assert len(block.body) == 1, (
            "%s does %d statements before main() can guard anything; the entry"
            " point must hand straight to main()" % (name, len(block.body)))
        stmt = block.body[0]
        calls = [n.func.id for n in ast.walk(stmt)
                 if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)]
        assert "main" in calls, (
            "%s's entry point does not call main(): %s" % (name, ast.dump(stmt)[:120]))


def test_no_hook_reads_stdin_at_import_time():
    """The guard lives in main(), so anything read BEFORE main() escapes it.

    The other tests import these modules once at the top of this file and only
    then install the counting stdin, so an import-time read happens while
    nothing is watching and every assertion still passes. Re-importing each
    module under the stub is what closes that -- without it the skill warns
    about a case its own verification cannot see.
    """
    import importlib
    for name in registered_hooks():
        def check(home, stdin, name=name):
            importlib.reload(importlib.import_module(name))
            assert stdin.reads == 0, (
                "%s reads stdin at import time, before main()'s guard can run"
                % name)
        in_drafter(check)


def test_every_registered_hook_has_a_guard_test():
    """The suite only runs tests it names, so a NEW hook added without a
    `test_<script>_is_inert` used to leave this file green while shipping an
    unguarded hook -- the verification passed with the procedure skipped,
    which is not a verification. Enumerate the registration instead.
    """
    scripts = registered_hooks()
    assert scripts, "no hook scripts found in hooks/hooks.json"
    missing = sorted(n for n in scripts
                     if "test_%s_is_inert" % n not in globals())
    assert not missing, (
        "hooks/hooks.json registers %s with no guard test; add"
        " test_<script>_is_inert for each (see the hook-inert-guard skill)"
        % ", ".join(missing))


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
